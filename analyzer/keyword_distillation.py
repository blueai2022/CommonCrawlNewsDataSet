#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Knowledge Distillation: Zero-Shot Model → Keyword Classifier

Strategy:
1. Score 5000 random articles with zero-shot model
2. For POSITIVE (+1) perspective:
   - HOT keywords: frequent in TOP 20% (high-score + high-confidence articles)
   - COLD keywords: frequent in BOTTOM 20% (low-score + high-confidence articles)
3. For NEGATIVE (-1) perspective:
   - HOT keywords: frequent in BOTTOM 20% (low-score + high-confidence articles)
   - COLD keywords: frequent in TOP 20% (high-score + high-confidence articles)
4. Remove person names (NER filtering)
5. Build separate regression models for +1 and -1 perspectives
6. Final score = average of both perspectives

This creates a BALANCED keyword classifier that works well for both extremes!
"""

import sqlite3
import pandas as pd
import numpy as np
from tqdm import tqdm
import logging
import re
from collections import Counter
import spacy
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import matplotlib.pyplot as plt
import seaborn as sns
import json
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load French NLP model for NER
try:
    nlp = spacy.load("fr_core_news_sm")
    logging.info("✓ Loaded spaCy French model")
except:
    logging.warning("⚠️  French spaCy model not found. Install with: python -m spacy download fr_core_news_sm")
    nlp = None


class KeywordDistillation:
    """Distill zero-shot model knowledge into keyword classifier."""
    
    def __init__(self, 
                 extreme_percentile=20,  # Changed: single parameter for both ends
                 min_confidence=0.75,
                 min_keyword_freq=5,
                 max_keywords=500):
        """
        Initialize distillation parameters.
        
        Args:
            extreme_percentile: Percentile for extremes (default: 20 = top/bottom 20%)
            min_confidence: Minimum confidence to include article (default: 0.75)
            min_keyword_freq: Minimum frequency across corpus (default: 5)
            max_keywords: Maximum keywords to keep per side (default: 500)
        """
        self.extreme_percentile = extreme_percentile
        self.min_confidence = min_confidence
        self.min_keyword_freq = min_keyword_freq
        self.max_keywords = max_keywords
        
        # Dual perspective storage
        self.positive_perspective = {}  # {dimension: {'hot': Counter, 'cold': Counter}}
        self.negative_perspective = {}  # {dimension: {'hot': Counter, 'cold': Counter}}
        
        self.regression_models = {}  # {dimension: {'positive': model, 'negative': model}}
        self.scalers = {}  # {dimension: {'positive': scaler, 'negative': scaler}}
        
    def extract_keywords(self, text, max_per_article=3):
        """
        Extract keywords from text, excluding person names.
        
        Args:
            text: Article text
            max_per_article: Max count per keyword per article
            
        Returns:
            Counter of keywords
        """
        # Convert to lowercase
        text_lower = text.lower()
        
        # Tokenize (keep only words with 3+ chars)
        words = re.findall(r'\b[a-zàâäéèêëïîôùûüÿæœç]{3,}\b', text_lower)
        
        # Count with max per article
        word_counts = Counter(words)
        capped_counts = Counter({
            word: min(count, max_per_article) 
            for word, count in word_counts.items()
        })
        
        # Remove person names using NER
        if nlp:
            doc = nlp(text[:10000])  # Limit length for speed
            person_names = set()
            for ent in doc.ents:
                if ent.label_ in ['PER', 'PERSON']:
                    person_names.add(ent.text.lower())
            
            # Remove identified names
            for name in person_names:
                name_words = name.split()
                for word in name_words:
                    if word in capped_counts:
                        del capped_counts[word]
        
        return capped_counts
    
    def identify_perspective_keywords(self, articles_df, dimension, perspective='positive'):
        """
        Identify keywords for ONE perspective (+1 or -1).
        
        REVISED APPROACH:
        - HOT keywords: High frequency in TOP 20%, Low frequency in BOTTOM 20%
        - COLD keywords: Low frequency in TOP 20%, High frequency in BOTTOM 20%
        - Ranking: HOT_count / COLD_count ratio (measures distinctiveness)
        - Minimum requirements:
          * HOT keywords need ≥5 occurrences in HOT pool
          * COLD keywords need ≥5 occurrences in COLD pool
          * Handle zeros with smoothing
        
        Args:
            articles_df: DataFrame with scores and confidence
            dimension: Dimension to analyze
            perspective: 'positive' or 'negative'
            
        Returns:
            dict: {'hot': Counter, 'cold': Counter}
        """
        score_col = f'{dimension}_score' if dimension != 'populism_composite' else 'populism_composite'
        conf_col = f'{dimension}_confidence' if dimension != 'populism_composite' else 'composite_confidence'
        
        # Filter by confidence
        high_conf = articles_df[articles_df[conf_col] >= self.min_confidence].copy()
        
        logging.info(f"\n📊 Analyzing {perspective.upper()} perspective for: {dimension}")
        logging.info(f"   High-confidence articles (≥{self.min_confidence}): {len(high_conf):,}")
        
        if len(high_conf) < 100:
            logging.warning(f"   ⚠️  Too few high-confidence articles! Using all articles.")
            high_conf = articles_df.copy()
        
        # Calculate percentiles (SAME for both perspectives!)
        top_threshold = np.percentile(high_conf[score_col], 100 - self.extreme_percentile)  # 80th percentile
        bottom_threshold = np.percentile(high_conf[score_col], self.extreme_percentile)     # 20th percentile
        
        logging.info(f"   Score range: [{high_conf[score_col].min():.3f}, {high_conf[score_col].max():.3f}]")
        logging.info(f"   Top {self.extreme_percentile}% threshold: ≥{top_threshold:.3f}")
        logging.info(f"   Bottom {self.extreme_percentile}% threshold: ≤{bottom_threshold:.3f}")
        
        # PERSPECTIVE-DEPENDENT SELECTION (using SAME thresholds!)
        if perspective == 'positive':
            # Positive perspective: TOP scores are HOT, BOTTOM scores are COLD
            hot_articles = high_conf[high_conf[score_col] >= top_threshold]
            cold_articles = high_conf[high_conf[score_col] <= bottom_threshold]
            logging.info(f"   HOT pool = TOP {self.extreme_percentile}%: {len(hot_articles):,} articles")
            logging.info(f"   COLD pool = BOTTOM {self.extreme_percentile}%: {len(cold_articles):,} articles")
        else:
            # Negative perspective: BOTTOM scores are HOT, TOP scores are COLD
            hot_articles = high_conf[high_conf[score_col] <= bottom_threshold]
            cold_articles = high_conf[high_conf[score_col] >= top_threshold]
            logging.info(f"   HOT pool = BOTTOM {self.extreme_percentile}% [INVERTED]: {len(hot_articles):,} articles")
            logging.info(f"   COLD pool = TOP {self.extreme_percentile}% [INVERTED]: {len(cold_articles):,} articles")
        
        # Extract keywords from HOT pool
        logging.info("   Extracting keywords from HOT pool...")
        hot_counts = Counter()
        for text in tqdm(hot_articles['text'], desc=f"Hot-{perspective}", leave=False):
            keywords = self.extract_keywords(text)
            hot_counts.update(keywords)
        
        # Extract keywords from COLD pool
        logging.info("   Extracting keywords from COLD pool...")
        cold_counts = Counter()
        for text in tqdm(cold_articles['text'], desc=f"Cold-{perspective}", leave=False):
            keywords = self.extract_keywords(text)
            cold_counts.update(keywords)
        
        # Get all words that appear in either pool
        all_words = set(hot_counts.keys()) | set(cold_counts.keys())
        
        logging.info(f"   Total unique words: {len(all_words):,}")
        
        # Calculate ratios for HOT candidates (must have ≥5 in HOT pool)
        hot_candidates = {}
        for word in all_words:
            hot_freq = hot_counts[word]
            cold_freq = cold_counts[word]
            
            # Must have at least 5 occurrences in HOT pool
            if hot_freq < self.min_keyword_freq:
                continue
            
            # Calculate ratio with smoothing (add 1 to avoid division by zero)
            ratio = (hot_freq + 1) / (cold_freq + 1)
            
            # Only keep if significantly more frequent in HOT (ratio > 4)
            if ratio > 4:
                hot_candidates[word] = {
                    'hot_count': hot_freq,
                    'cold_count': cold_freq,
                    'ratio': ratio
                }
        
        # Calculate ratios for COLD candidates (must have ≥5 in COLD pool)
        cold_candidates = {}
        for word in all_words:
            hot_freq = hot_counts[word]
            cold_freq = cold_counts[word]
            
            # Must have at least 5 occurrences in COLD pool
            if cold_freq < self.min_keyword_freq:
                continue
            
            # Calculate inverse ratio (COLD/HOT)
            ratio = (cold_freq + 1) / (hot_freq + 1)
            
            # Only keep if significantly more frequent in COLD (ratio > 4)
            if ratio > 4:
                cold_candidates[word] = {
                    'hot_count': hot_freq,
                    'cold_count': cold_freq,
                    'ratio': ratio
                }
        
        logging.info(f"   HOT candidates (≥{self.min_keyword_freq} in HOT, ratio>4): {len(hot_candidates):,}")
        logging.info(f"   COLD candidates (≥{self.min_keyword_freq} in COLD, ratio>4): {len(cold_candidates):,}")
        
        # Sort by ratio and keep top N
        hot_sorted = sorted(hot_candidates.items(), key=lambda x: x[1]['ratio'], reverse=True)
        cold_sorted = sorted(cold_candidates.items(), key=lambda x: x[1]['ratio'], reverse=True)
        
        # Build final keyword sets
        hot_keywords = Counter()
        for word, stats in hot_sorted[:self.max_keywords]:
            hot_keywords[word] = stats['hot_count']
        
        cold_keywords = Counter()
        for word, stats in cold_sorted[:self.max_keywords]:
            cold_keywords[word] = stats['cold_count']
        
        logging.info(f"   Final HOT keywords: {len(hot_keywords):,}")
        logging.info(f"   Final COLD keywords: {len(cold_keywords):,}")
        
        # Show statistics for top keywords
        if hot_keywords:
            logging.info(f"\n   Top 10 HOT keywords:")
            for word in list(hot_keywords.keys())[:10]:
                stats = hot_sorted[[w for w, _ in hot_sorted].index(word)][1]
                logging.info(f"      {word:20s}: hot={stats['hot_count']:3d}, cold={stats['cold_count']:3d}, ratio={stats['ratio']:.2f}")
        
        if cold_keywords:
            logging.info(f"\n   Top 10 COLD keywords:")
            for word in list(cold_keywords.keys())[:10]:
                stats = cold_sorted[[w for w, _ in cold_sorted].index(word)][1]
                logging.info(f"      {word:20s}: hot={stats['hot_count']:3d}, cold={stats['cold_count']:3d}, ratio={stats['ratio']:.2f}")
        
        return {
            'hot': hot_keywords,
            'cold': cold_keywords
        }
    
    def build_feature_matrix(self, articles_df, dimension, perspective='positive'):
        """
        Build feature matrix from keyword counts for one perspective.
        
        Args:
            articles_df: DataFrame with text column
            dimension: Dimension name
            perspective: 'positive' or 'negative'
            
        Returns:
            tuple: (feature_matrix, feature_names)
        """
        if perspective == 'positive':
            kw_data = self.positive_perspective[dimension]
        else:
            kw_data = self.negative_perspective[dimension]
        
        hot_kw = kw_data['hot']
        cold_kw = kw_data['cold']
        
        all_keywords = list(hot_kw.keys()) + list(cold_kw.keys())
        
        logging.info(f"\n🔨 Building feature matrix for {dimension} ({perspective} perspective)")
        logging.info(f"   Total keywords: {len(all_keywords):,}")
        
        # Count keywords in each article
        feature_matrix = []
        
        for text in tqdm(articles_df['text'], desc=f"Features-{perspective}", leave=False):
            keywords = self.extract_keywords(text, max_per_article=10)
            
            # Count hot keywords
            hot_count = sum(keywords.get(kw, 0) for kw in hot_kw)
            
            # Count cold keywords
            cold_count = sum(keywords.get(kw, 0) for kw in cold_kw)
            
            # Individual keyword features
            keyword_features = [keywords.get(kw, 0) for kw in all_keywords]
            
            # Combined features
            features = [hot_count, cold_count] + keyword_features
            feature_matrix.append(features)
        
        feature_names = ['hot_count', 'cold_count'] + all_keywords
        
        return np.array(feature_matrix), feature_names
    
    def train_regression(self, articles_df, dimension='populism_composite'):
        """
        Train TWO regression models: one for +1 perspective, one for -1 perspective.
        
        Final prediction = average of both models.
        """
        score_col = f'{dimension}_score' if dimension != 'populism_composite' else 'populism_composite'
        
        logging.info(f"\n🎯 Training DUAL regression models for {dimension}")
        
        results = {}
        
        for perspective in ['positive', 'negative']:
            logging.info(f"\n   Training {perspective.upper()} perspective model...")
            
            # Build features
            X, feature_names = self.build_feature_matrix(articles_df, dimension, perspective)
            y = articles_df[score_col].values
            
            # Split train/test
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train Ridge regression
            model = Ridge(alpha=1.0)
            model.fit(X_train_scaled, y_train)
            
            # Evaluate
            y_pred_train = model.predict(X_train_scaled)
            y_pred_test = model.predict(X_test_scaled)
            
            train_r2 = r2_score(y_train, y_pred_train)
            test_r2 = r2_score(y_test, y_pred_test)
            train_rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
            test_rmse = np.sqrt(mean_squared_error(y_test, y_pred_test))
            
            logging.info(f"      Training R²: {train_r2:.4f}, RMSE: {train_rmse:.4f}")
            logging.info(f"      Test R²: {test_r2:.4f}, RMSE: {test_rmse:.4f}")
            
            # Store model
            if dimension not in self.regression_models:
                self.regression_models[dimension] = {}
                self.scalers[dimension] = {}
            
            self.regression_models[dimension][perspective] = model
            self.scalers[dimension][perspective] = scaler
            
            # Show top features
            coefs = model.coef_
            top_positive = np.argsort(coefs)[-5:][::-1]
            top_negative = np.argsort(coefs)[:5]
            
            logging.info(f"\n      Top 5 positive features:")
            for idx in top_positive:
                logging.info(f"         {feature_names[idx]:20s}: {coefs[idx]:+.4f}")
            
            logging.info(f"\n      Top 5 negative features:")
            for idx in top_negative:
                logging.info(f"         {feature_names[idx]:20s}: {coefs[idx]:+.4f}")
            
            results[perspective] = {
                'train_r2': train_r2,
                'test_r2': test_r2,
                'train_rmse': train_rmse,
                'test_rmse': test_rmse
            }
        
        return results
    
    def predict(self, text, dimension='populism_composite'):
        """
        Predict score using BOTH perspectives and average them.
        
        This balances the model for both +1 and -1 extremes!
        """
        if dimension not in self.regression_models:
            raise ValueError(f"No model trained for dimension: {dimension}")
        
        predictions = []
        
        for perspective in ['positive', 'negative']:
            # Get keywords for this perspective
            if perspective == 'positive':
                kw_data = self.positive_perspective[dimension]
            else:
                kw_data = self.negative_perspective[dimension]
            
            hot_kw = kw_data['hot']
            cold_kw = kw_data['cold']
            all_keywords = list(hot_kw.keys()) + list(cold_kw.keys())
            
            # Extract features
            keywords = self.extract_keywords(text, max_per_article=10)
            hot_count = sum(keywords.get(kw, 0) for kw in hot_kw)
            cold_count = sum(keywords.get(kw, 0) for kw in cold_kw)
            keyword_features = [keywords.get(kw, 0) for kw in all_keywords]
            
            X = np.array([[hot_count, cold_count] + keyword_features])
            
            # Scale and predict
            X_scaled = self.scalers[dimension][perspective].transform(X)
            pred = self.regression_models[dimension][perspective].predict(X_scaled)[0]
            predictions.append(pred)
        
        # Average both perspectives
        final_score = np.mean(predictions)
        
        return round(final_score, 4)
    
    def save_model(self, output_path='keyword_populism_model_dual.json'):
        """Save dual-perspective keyword model with complete feature structure."""
        data = {
            'positive_perspective': {
                dim: {
                    'hot': dict(kw['hot']),
                    'cold': dict(kw['cold']),
                    # Save ordered keyword list for feature matrix
                    'feature_order': list(kw['hot'].keys()) + list(kw['cold'].keys())
                }
                for dim, kw in self.positive_perspective.items()
            },
            'negative_perspective': {
                dim: {
                    'hot': dict(kw['hot']),
                    'cold': dict(kw['cold']),
                    # Save ordered keyword list for feature matrix
                    'feature_order': list(kw['hot'].keys()) + list(kw['cold'].keys())
                }
                for dim, kw in self.negative_perspective.items()
            },
            'parameters': {
                'extreme_percentile': self.extreme_percentile,
                'min_confidence': self.min_confidence
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logging.info(f"✅ Saved dual-perspective keyword model to: {output_path}")
        
        # Also save regression models separately
        if self.regression_models:
            self.save_regression_models('keyword_regression_models.pkl')
    
    def save_regression_models(self, output_path='keyword_regression_models.pkl'):
        """
        Save regression models with their exact feature structure.
        
        CRITICAL: Feature order must match between training and prediction!
        """
        import pickle
        
        models_data = {
            'models': self.regression_models,
            'scalers': self.scalers,
            'feature_structure': {}  # Maps dimension -> perspective -> [feature_names]
        }
        
        # Save feature structure for each dimension and perspective
        for dimension in self.positive_perspective:
            models_data['feature_structure'][dimension] = {}
            
            for perspective in ['positive', 'negative']:
                if perspective == 'positive':
                    kw_data = self.positive_perspective[dimension]
                else:
                    kw_data = self.negative_perspective[dimension]
                
                hot_kw = kw_data['hot']
                cold_kw = kw_data['cold']
                
                # EXACT ORDER used during training
                all_keywords = list(hot_kw.keys()) + list(cold_kw.keys())
                feature_names = ['hot_count', 'cold_count'] + all_keywords
                
                models_data['feature_structure'][dimension][perspective] = feature_names
        
        with open(output_path, 'wb') as f:
            pickle.dump(models_data, f)
        
        file_size_mb = os.path.getsize(output_path) / 1024 / 1024
        logging.info(f"✅ Saved regression models to: {output_path}")
        logging.info(f"   File size: {file_size_mb:.2f} MB")
        
        # Verify feature structure
        for dim in models_data['feature_structure']:
            for persp in models_data['feature_structure'][dim]:
                n_features = len(models_data['feature_structure'][dim][persp])
                logging.info(f"   {dim} ({persp}): {n_features} features")


def visualize_results(articles_df, distiller, dimensions=['populism_composite']):
    """Visualize dual-perspective model performance."""
    
    n_dims = len(dimensions)
    fig, axes = plt.subplots(2, n_dims, figsize=(8*n_dims, 12))
    
    if n_dims == 1:
        axes = axes.reshape(2, 1)
    
    for idx, dimension in enumerate(dimensions):
        score_col = f'{dimension}_score' if dimension != 'populism_composite' else 'populism_composite'
        
        # Get predictions
        logging.info(f"Generating predictions for visualization: {dimension}")
        predictions = []
        for text in tqdm(articles_df['text'][:1000], desc=f"Predicting {dimension}", leave=False):
            pred = distiller.predict(text, dimension)
            predictions.append(pred)
        
        actual = articles_df[score_col].values[:1000]
        predictions = np.array(predictions)  # Convert to numpy array for indexing
        
        # Plot 1: Full scatter
        ax = axes[0, idx]
        ax.scatter(actual, predictions, alpha=0.3, s=20)
        ax.plot([-1, 1], [-1, 1], 'r--', linewidth=2, label='Perfect prediction')
        
        r2 = r2_score(actual, predictions)
        rmse = np.sqrt(mean_squared_error(actual, predictions))
        
        ax.set_xlabel('Zero-Shot Model Score', fontsize=12)
        ax.set_ylabel('Dual-Perspective Keyword Score', fontsize=12)
        ax.set_title(f'{dimension}\nR² = {r2:.3f}, RMSE = {rmse:.3f}', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(alpha=0.3)
        
        # Plot 2: Separate by score sign
        ax = axes[1, idx]
        positive_mask = actual > 0
        negative_mask = actual < 0
        
        ax.scatter(actual[positive_mask], predictions[positive_mask], 
                  alpha=0.4, s=20, c='blue', label=f'Positive (n={positive_mask.sum()})')
        ax.scatter(actual[negative_mask], predictions[negative_mask], 
                  alpha=0.4, s=20, c='red', label=f'Negative (n={negative_mask.sum()})')
        ax.plot([-1, 1], [-1, 1], 'k--', linewidth=2, alpha=0.5)
        
        # Calculate R² for each side
        r2_pos = r2_score(actual[positive_mask], predictions[positive_mask]) if positive_mask.sum() > 0 else 0
        r2_neg = r2_score(actual[negative_mask], predictions[negative_mask]) if negative_mask.sum() > 0 else 0
        
        ax.set_xlabel('Zero-Shot Score', fontsize=12)
        ax.set_ylabel('Keyword Score', fontsize=12)
        ax.set_title(f'By Sign: R²(+) = {r2_pos:.3f}, R²(-) = {r2_neg:.3f}', fontsize=12, fontweight='bold')
        ax.legend()
        ax.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('keyword_model_dual_validation.png', dpi=150, bbox_inches='tight')
    logging.info("✅ Saved visualization: keyword_model_dual_validation.png")


def main(db_path, sample_size=5000):
    """Main dual-perspective distillation pipeline."""
    
    logging.info("=" * 70)
    logging.info("🔬 DUAL-PERSPECTIVE KEYWORD DISTILLATION PIPELINE")
    logging.info("   Using consistent 80/20 split for both perspectives")
    logging.info("=" * 70)
    
    # Load scored articles
    logging.info(f"\n📖 Loading {sample_size:,} articles with zero-shot scores...")
    
    if os.path.exists('test_results_articles_fast.csv'):
        logging.info("   Found existing scored articles!")
        articles_df = pd.read_csv('test_results_articles_fast.csv')
        
        if len(articles_df) < sample_size:
            logging.warning(f"   Only {len(articles_df):,} articles available")
            sample_size = len(articles_df)
    else:
        logging.error("   ❌ No scored articles found! Run zero-shot scoring first:")
        logging.error("      python populism_zeroshot_fast.py <db> output.csv --sample 5000")
        logging.error("   OR generate synthetic test data:")
        logging.error(f"      python generate_test_data.py {db_path} {sample_size}")
        return
    
    # Check if text column exists
    if 'text' not in articles_df.columns:
        logging.info("   Text not in CSV, loading from database...")
        conn = sqlite3.connect(db_path)
        text_df = pd.read_sql(f"""
            SELECT id, text 
            FROM Articles 
            WHERE id IN ({','.join([f"'{x}'" for x in articles_df['article_id'].values])})
        """, conn)
        conn.close()
        
        articles_df = articles_df.merge(text_df, left_on='article_id', right_on='id', how='inner')
        logging.info(f"   Loaded {len(articles_df):,} articles with text")
    else:
        logging.info(f"   Using text from CSV: {len(articles_df):,} articles")
    
    # Verify we have required columns
    required_cols = ['text', 'anti_estab_score', 'anti_estab_confidence', 
                     'econ_nat_score', 'econ_nat_confidence',
                     'people_centric_score', 'people_centric_confidence',
                     'populism_composite', 'composite_confidence']
    
    missing_cols = [col for col in required_cols if col not in articles_df.columns]
    if missing_cols:
        logging.error(f"   ❌ Missing required columns: {missing_cols}")
        logging.error("   Please regenerate the scored articles CSV")
        return
    
    logging.info(f"   ✅ All required columns present")
    
    # Initialize distiller with 80/20 split
    distiller = KeywordDistillation(
        extreme_percentile=20,  # Top/bottom 20% (80th and 20th percentiles)
        min_confidence=0.75,
        min_keyword_freq=5,
        max_keywords=500
    )
    
    # Extract keywords for BOTH perspectives
    dimensions = ['anti_estab', 'econ_nat', 'people_centric', 'populism_composite']
    
    for dimension in dimensions:
        # Positive perspective (+1): TOP 20% = HOT, BOTTOM 20% = COLD
        pos_kw = distiller.identify_perspective_keywords(articles_df, dimension, 'positive')
        distiller.positive_perspective[dimension] = pos_kw
        
        # Negative perspective (-1): BOTTOM 20% = HOT, TOP 20% = COLD (inverted!)
        neg_kw = distiller.identify_perspective_keywords(articles_df, dimension, 'negative')
        distiller.negative_perspective[dimension] = neg_kw
    
    # Train dual models
    results = {}
    for dimension in dimensions:
        results[dimension] = distiller.train_regression(articles_df, dimension)
    
    # Save model
    distiller.save_model('keyword_populism_model_dual.json')
    
    # Visualize
    visualize_results(articles_df, distiller, dimensions)
    
    logging.info("\n" + "=" * 70)
    logging.info("✅ DUAL-PERSPECTIVE DISTILLATION COMPLETE!")
    logging.info("=" * 70)
    logging.info("\n💡 Key improvements:")
    logging.info("   - Consistent 80/20 split (same thresholds for both perspectives)")
    logging.info("   - Separate keyword sets for +1 and -1 perspectives")
    logging.info("   - Balanced accuracy at both extremes")
    logging.info("   - Final score = average of both models")
    logging.info("\n📁 Output files:")
    logging.info("   - keyword_populism_model_dual.json (keyword lists)")
    logging.info("   - keyword_regression_models.pkl (trained models)")
    logging.info("   - keyword_model_dual_validation.png (performance plots)")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python keyword_distillation.py <db_path> [sample_size]")
        print("\nRequires: Pre-scored articles from zero-shot model")
        print("   Run first: python populism_zeroshot_fast.py <db> output.csv --sample 5000")
        print("   OR generate synthetic test data:")
        print("      python generate_test_data.py <db> <sample_size>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    sample_size = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    
    main(db_path, sample_size)