#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Political Sentiment Analysis for French News Articles

Classifies articles on a political spectrum:
  +1: Nationalist/Conservative values
  -1: Liberal/Progressive values
   0: Neutral/Balanced

Uses French language transformers for sentiment and political stance detection.
"""

import sqlite3
import pandas as pd
import numpy as np
import torch
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification,
    pipeline
)
from tqdm import tqdm
import logging
from argparse import ArgumentParser
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class FrenchPoliticalAnalyzer:
    """Analyze political stance of French text using transformers."""
    
    def __init__(self, model_name: str = "cmarkea/distilcamembert-base-sentiment", 
                 device: str = None, batch_size: int = 8):
        """
        Initialize the political analyzer.
        
        Args:
            model_name: HuggingFace model for French sentiment analysis
            device: 'cuda', 'cpu', or None (auto-detect)
            batch_size: Number of texts to process at once
        """
        self.batch_size = batch_size
        
        # Auto-detect device
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        logging.info(f"Using device: {self.device}")
        
        # Load sentiment model for initial filtering
        logging.info(f"Loading sentiment model: {model_name}")
        self.sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model=model_name,
            device=0 if self.device == "cuda" else -1,
            batch_size=batch_size
        )
        
        # Political keywords for French context
        self.conservative_keywords = {
            # Nationalism/Patriotism
            'nation', 'patrie', 'patriote', 'nationalisme', 'souveraineté', 
            'identité nationale', 'frontières', 'immigration contrôlée',
            # Traditional values
            'tradition', 'famille traditionnelle', 'valeurs chrétiennes',
            'ordre', 'autorité', 'sécurité', 'loi et ordre',
            # Economic conservatism
            'libre entreprise', 'déréglementation', 'baisse d\'impôts',
            # Right-wing parties/figures
            'le pen', 'rassemblement national', 'fn', 'front national',
            'zemmour', 'républicains', 'droite', 'conservateur',
        }
        
        self.progressive_keywords = {
            # Social progressivism
            'égalité', 'diversité', 'inclusion', 'tolérance', 'solidarité',
            'droits humains', 'justice sociale', 'féminisme', 'antiracisme',
            # Immigration/multiculturalism
            'accueil', 'réfugiés', 'multiculturalisme', 'intégration',
            # Economic progressivism
            'redistribution', 'état providence', 'services publics',
            'régulation', 'impôts progressifs', 'justice fiscale',
            # Left-wing parties/figures
            'mélenchon', 'insoumis', 'lfi', 'parti socialiste', 'ps',
            'gauche', 'progressiste', 'socialiste', 'écologiste', 'eelv',
        }
        
        self.neutral_indicators = {
            'économie', 'éducation', 'santé', 'emploi', 'technologie',
            'science', 'météo', 'sport', 'culture', 'art',
        }
        
    def analyze_text(self, text: str) -> dict:
        """
        Analyze a single text for political stance.
        
        Returns:
            dict with 'score' (-1 to +1), 'confidence', and 'label'
        """
        if not text or len(text.strip()) < 50:
            return {'score': 0.0, 'confidence': 0.0, 'label': 'neutral', 'reason': 'too_short'}
        
        text_lower = text.lower()
        
        # Count keyword occurrences
        conservative_count = sum(1 for kw in self.conservative_keywords if kw in text_lower)
        progressive_count = sum(1 for kw in self.progressive_keywords if kw in text_lower)
        neutral_count = sum(1 for kw in self.neutral_indicators if kw in text_lower)
        
        # Calculate base score from keywords
        total_political = conservative_count + progressive_count
        
        if total_political == 0:
            # No political keywords - likely neutral
            return {'score': 0.0, 'confidence': 0.8, 'label': 'neutral', 
                    'reason': 'no_political_keywords'}
        
        # Calculate political leaning
        if conservative_count > progressive_count:
            keyword_score = min(1.0, conservative_count / (total_political * 0.5))
        elif progressive_count > conservative_count:
            keyword_score = -min(1.0, progressive_count / (total_political * 0.5))
        else:
            keyword_score = 0.0
        
        # Get sentiment (helps calibrate intensity)
        try:
            # Truncate to model's max length (512 tokens ~= 2000 chars for safety)
            text_truncated = text[:2000]
            sentiment = self.sentiment_pipeline(text_truncated)[0]
            
            # Sentiment labels vary by model, normalize them
            sentiment_score = 0.0
            if sentiment['label'].lower() in ['positive', '5 stars', 'pos']:
                sentiment_score = sentiment['score']
            elif sentiment['label'].lower() in ['negative', '1 star', 'neg']:
                sentiment_score = -sentiment['score']
            # else: neutral sentiment
            
        except Exception as e:
            logging.warning(f"Sentiment analysis failed: {e}")
            sentiment_score = 0.0
        
        # Combine keyword-based score with sentiment intensity
        # Sentiment modulates the confidence, not the direction
        final_score = keyword_score * (0.5 + 0.5 * abs(sentiment_score))
        
        # Clip to [-1, 1]
        final_score = max(-1.0, min(1.0, final_score))
        
        # Determine label
        if final_score > 0.3:
            label = 'conservative'
        elif final_score < -0.3:
            label = 'progressive'
        else:
            label = 'neutral'
        
        # Confidence based on keyword count and sentiment confidence
        confidence = min(1.0, (total_political / 10.0) * 0.5 + 
                        abs(sentiment_score) * 0.5)
        
        return {
            'score': round(final_score, 3),
            'confidence': round(confidence, 3),
            'label': label,
            'conservative_kw': conservative_count,
            'progressive_kw': progressive_count,
            'neutral_kw': neutral_count
        }
    
    def analyze_batch(self, texts: list) -> list:
        """Analyze multiple texts efficiently."""
        results = []
        for text in tqdm(texts, desc="Analyzing texts", disable=len(texts) < 10):
            results.append(self.analyze_text(text))
        return results


def process_database(db_path: str, output_path: str = None, 
                     limit: int = None, batch_size: int = 8):
    """
    Process all articles in SQLite database and add political scores.
    
    Args:
        db_path: Path to SQLite database
        output_path: Path to save results (optional, updates DB if None)
        limit: Limit number of articles to process (for testing)
        batch_size: Batch size for processing
    """
    logging.info("=" * 70)
    logging.info("🗳️  French Political Sentiment Analysis")
    logging.info("=" * 70)
    logging.info(f"Database: {db_path}")
    logging.info(f"Batch size: {batch_size}")
    if limit:
        logging.info(f"Limit: {limit:,} articles")
    logging.info("")
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    
    # Read articles
    query = "SELECT id, title, text FROM Articles"
    if limit:
        query += f" LIMIT {limit}"
    
    logging.info("📖 Reading articles from database...")
    df = pd.read_sql(query, conn)
    logging.info(f"   Loaded {len(df):,} articles")
    logging.info("")
    
    # Initialize analyzer
    analyzer = FrenchPoliticalAnalyzer(batch_size=batch_size)
    
    # Analyze articles
    logging.info("🔍 Analyzing political stance...")
    
    # Combine title and text for better context (truncate to avoid huge texts)
    df['full_text'] = df['title'].fillna('') + '\n\n' + df['text'].fillna('')
    df['full_text'] = df['full_text'].str[:5000]  # Limit to ~5000 chars
    
    results = analyzer.analyze_batch(df['full_text'].tolist())
    
    # Add results to dataframe
    df['political_score'] = [r['score'] for r in results]
    df['political_confidence'] = [r['confidence'] for r in results]
    df['political_label'] = [r['label'] for r in results]
    df['conservative_keywords'] = [r['conservative_kw'] for r in results]
    df['progressive_keywords'] = [r['progressive_kw'] for r in results]
    
    # Drop the temporary full_text column
    df = df.drop('full_text', axis=1)
    
    logging.info("")
    logging.info("=" * 70)
    logging.info("📊 Results Summary")
    logging.info("=" * 70)
    
    # Distribution statistics
    label_counts = df['political_label'].value_counts()
    logging.info(f"\nLabel Distribution:")
    for label, count in label_counts.items():
        pct = count / len(df) * 100
        logging.info(f"  {label:12s}: {count:6,} ({pct:5.1f}%)")
    
    # Score statistics
    logging.info(f"\nScore Statistics:")
    logging.info(f"  Mean:   {df['political_score'].mean():+.3f}")
    logging.info(f"  Median: {df['political_score'].median():+.3f}")
    logging.info(f"  Std:    {df['political_score'].std():.3f}")
    logging.info(f"  Min:    {df['political_score'].min():+.3f}")
    logging.info(f"  Max:    {df['political_score'].max():+.3f}")
    
    # Confidence statistics
    logging.info(f"\nConfidence Statistics:")
    logging.info(f"  Mean:   {df['political_confidence'].mean():.3f}")
    logging.info(f"  Median: {df['political_confidence'].median():.3f}")
    
    # Show sample results
    logging.info(f"\nSample Results (Top 5 Conservative):")
    top_conservative = df.nlargest(5, 'political_score')[['title', 'political_score', 'political_label']]
    for _, row in top_conservative.iterrows():
        logging.info(f"  [{row['political_score']:+.2f}] {row['title'][:60]}...")
    
    logging.info(f"\nSample Results (Top 5 Progressive):")
    top_progressive = df.nsmallest(5, 'political_score')[['title', 'political_score', 'political_label']]
    for _, row in top_progressive.iterrows():
        logging.info(f"  [{row['political_score']:+.2f}] {row['title'][:60]}...")
    
    # Save results
    if output_path:
        logging.info(f"\n💾 Saving results to: {output_path}")
        
        # Determine format from extension
        output_path = Path(output_path)
        if output_path.suffix == '.csv':
            df.to_csv(output_path, index=False)
        elif output_path.suffix == '.feather':
            df.to_feather(output_path)
        elif output_path.suffix in ['.xlsx', '.xls']:
            df.to_excel(output_path, index=False)
        else:
            # Default to CSV
            df.to_csv(output_path.with_suffix('.csv'), index=False)
        
        logging.info(f"   ✅ Saved {len(df):,} articles")
    else:
        # Update database
        logging.info(f"\n💾 Updating database with political scores...")
        
        # Add columns if they don't exist
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(Articles)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        
        if 'political_score' not in existing_cols:
            cursor.execute("ALTER TABLE Articles ADD COLUMN political_score REAL")
        if 'political_confidence' not in existing_cols:
            cursor.execute("ALTER TABLE Articles ADD COLUMN political_confidence REAL")
        if 'political_label' not in existing_cols:
            cursor.execute("ALTER TABLE Articles ADD COLUMN political_label TEXT")
        
        # Update rows
        for _, row in tqdm(df.iterrows(), total=len(df), desc="Updating database"):
            cursor.execute("""
                UPDATE Articles 
                SET political_score = ?,
                    political_confidence = ?,
                    political_label = ?
                WHERE id = ?
            """, (row['political_score'], row['political_confidence'], 
                  row['political_label'], row['id']))
        
        conn.commit()
        logging.info(f"   ✅ Updated {len(df):,} articles in database")
    
    conn.close()
    
    logging.info("")
    logging.info("✅ Analysis complete!")
    logging.info("=" * 70)


def main():
    parser = ArgumentParser(description="Political sentiment analysis for French news articles.")
    parser.add_argument("db_path", type=str, help="Path to SQLite database")
    parser.add_argument("--output", type=str, default=None,
                       help="Output file (CSV/Excel/Feather). If not specified, updates database in-place.")
    parser.add_argument("--limit", type=int, default=None,
                       help="Limit number of articles to process (for testing)")
    parser.add_argument("--batch-size", type=int, default=8,
                       help="Batch size for processing (default: 8, reduce if OOM)")
    
    args = parser.parse_args()
    
    process_database(
        db_path=args.db_path,
        output_path=args.output,
        limit=args.limit,
        batch_size=args.batch_size
    )


if __name__ == "__main__":
    main()