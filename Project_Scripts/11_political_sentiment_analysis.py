#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Political Sentiment Analysis for French News Articles - Enhanced Version

Classifies articles on a political spectrum using zero-shot classification:
  +1: Nationalist/Conservative values
  -1: Liberal/Progressive values
   0: Neutral/Balanced

Uses multi-label classification with French language models for fine-grained scoring.
"""

import sqlite3
import pandas as pd
import numpy as np
import torch
from transformers import pipeline
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
    """Analyze political stance using zero-shot classification and multi-aspect scoring."""
    
    def __init__(self, device: str = None, batch_size: int = 4):
        """
        Initialize the political analyzer with zero-shot classification.
        
        Args:
            device: 'cuda', 'cpu', or None (auto-detect)
            batch_size: Number of texts to process at once (lower for zero-shot)
        """
        self.batch_size = batch_size
        
        # Auto-detect device
        if device is None:
            self.device = 0 if torch.cuda.is_available() else -1
        else:
            self.device = 0 if device == "cuda" else -1
            
        device_name = "GPU" if self.device == 0 else "CPU"
        logging.info(f"Using device: {device_name}")
        
        # Load zero-shot classification model for French
        logging.info("Loading zero-shot classification model (may take a few minutes)...")
        try:
            # Use multilingual model that works well with French
            self.classifier = pipeline(
                "zero-shot-classification",
                model="MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
                device=self.device
            )
            logging.info("✅ Model loaded successfully")
        except Exception as e:
            logging.error(f"Failed to load model: {e}")
            logging.info("Falling back to simpler model...")
            self.classifier = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=self.device
            )
        
        # Define political dimensions with French labels
        # Each dimension has opposing stances that we'll compare
        self.political_dimensions = {
            'nationalism': {
                'conservative': [
                    "défense de la souveraineté nationale",
                    "contrôle strict de l'immigration",
                    "protection de l'identité française",
                    "priorité nationale",
                    "fermeture des frontières"
                ],
                'progressive': [
                    "ouverture aux réfugiés",
                    "multiculturalisme",
                    "intégration européenne",
                    "solidarité internationale",
                    "libre circulation"
                ]
            },
            'social_values': {
                'conservative': [
                    "valeurs traditionnelles",
                    "famille traditionnelle",
                    "ordre et autorité",
                    "sécurité avant tout",
                    "respect des traditions"
                ],
                'progressive': [
                    "égalité des genres",
                    "droits LGBTQ+",
                    "diversité culturelle",
                    "libertés individuelles",
                    "justice sociale"
                ]
            },
            'economics': {
                'conservative': [
                    "libre entreprise",
                    "baisse des impôts",
                    "réduction des dépenses publiques",
                    "déréglementation",
                    "responsabilité individuelle"
                ],
                'progressive': [
                    "redistribution des richesses",
                    "services publics renforcés",
                    "régulation économique",
                    "impôts progressifs",
                    "protection sociale"
                ]
            }
        }
        
    def analyze_text(self, text: str, title: str = "") -> dict:
        """
        Analyze text for political stance across multiple dimensions.
        
        Returns:
            dict with overall score, dimension scores, and confidence
        """
        if not text or len(text.strip()) < 100:
            return {
                'score': 0.0,
                'confidence': 0.0,
                'label': 'neutral',
                'dimensions': {},
                'reason': 'too_short'
            }
        
        # Combine title and excerpt for better context
        full_text = f"{title}\n\n{text[:3000]}"  # Limit to avoid model max length
        
        dimension_scores = {}
        dimension_confidences = {}
        
        try:
            # Analyze each political dimension
            for dimension, labels in self.political_dimensions.items():
                # Combine all labels for this dimension
                all_labels = labels['conservative'] + labels['progressive']
                
                # Run zero-shot classification
                result = self.classifier(
                    full_text,
                    candidate_labels=all_labels,
                    multi_label=True  # Allow multiple labels to apply
                )
                
                # Calculate dimension score
                conservative_score = 0.0
                progressive_score = 0.0
                total_confidence = 0.0
                
                for label, score in zip(result['labels'], result['scores']):
                    if label in labels['conservative']:
                        conservative_score += score
                    elif label in labels['progressive']:
                        progressive_score += score
                    total_confidence += score
                
                # Normalize scores
                if total_confidence > 0:
                    conservative_score /= len(labels['conservative'])
                    progressive_score /= len(labels['progressive'])
                    
                    # Calculate dimension score: -1 (progressive) to +1 (conservative)
                    if conservative_score + progressive_score > 0:
                        dim_score = (conservative_score - progressive_score) / (conservative_score + progressive_score)
                    else:
                        dim_score = 0.0
                    
                    dimension_scores[dimension] = round(dim_score, 3)
                    dimension_confidences[dimension] = round(
                        (conservative_score + progressive_score) / 2, 3
                    )
                else:
                    dimension_scores[dimension] = 0.0
                    dimension_confidences[dimension] = 0.0
            
            # Calculate overall score (weighted average)
            # Weight: nationalism (0.4), social values (0.3), economics (0.3)
            weights = {
                'nationalism': 0.4,
                'social_values': 0.3,
                'economics': 0.3
            }
            
            overall_score = sum(
                dimension_scores.get(dim, 0) * weight 
                for dim, weight in weights.items()
            )
            
            overall_confidence = np.mean([
                dimension_confidences.get(dim, 0) 
                for dim in weights.keys()
            ])
            
            # Determine label based on score
            if overall_score > 0.2:
                label = 'conservative'
            elif overall_score < -0.2:
                label = 'progressive'
            else:
                label = 'neutral'
            
            return {
                'score': round(overall_score, 3),
                'confidence': round(overall_confidence, 3),
                'label': label,
                'dimensions': dimension_scores,
                'dimension_confidences': dimension_confidences
            }
            
        except Exception as e:
            logging.warning(f"Analysis failed: {e}")
            return {
                'score': 0.0,
                'confidence': 0.0,
                'label': 'neutral',
                'dimensions': {},
                'reason': f'error: {str(e)}'
            }
    
    def analyze_batch(self, texts: list, titles: list = None) -> list:
        """Analyze multiple texts (with progress bar)."""
        if titles is None:
            titles = [""] * len(texts)
        
        results = []
        for text, title in tqdm(
            zip(texts, titles), 
            total=len(texts), 
            desc="Analyzing political stance"
        ):
            results.append(self.analyze_text(text, title))
        
        return results


def process_database(db_path: str, output_path: str = None, 
                     limit: int = None, batch_size: int = 4):
    """
    Process all articles in SQLite database and add political scores.
    
    Args:
        db_path: Path to SQLite database
        output_path: Path to save results (optional, updates DB if None)
        limit: Limit number of articles to process (for testing)
        batch_size: Batch size for processing (keep low for zero-shot)
    """
    logging.info("=" * 70)
    logging.info("🗳️  French Political Sentiment Analysis (Enhanced)")
    logging.info("=" * 70)
    logging.info(f"Database: {db_path}")
    logging.info(f"Batch size: {batch_size}")
    if limit:
        logging.info(f"Limit: {limit:,} articles")
    logging.info("")
    logging.info("Using zero-shot classification for fine-grained political scoring")
    logging.info("This may take longer but provides more accurate results...")
    logging.info("")
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    
    # Read articles
    query = "SELECT id, title, text FROM Articles WHERE text IS NOT NULL AND LENGTH(text) > 100"
    if limit:
        query += f" LIMIT {limit}"
    
    logging.info("📖 Reading articles from database...")
    df = pd.read_sql(query, conn)
    logging.info(f"   Loaded {len(df):,} articles")
    logging.info("")
    
    # Initialize analyzer
    analyzer = FrenchPoliticalAnalyzer(batch_size=batch_size)
    
    # Analyze articles
    logging.info("🔍 Analyzing political stance across multiple dimensions...")
    logging.info("   Dimensions: Nationalism, Social Values, Economics")
    logging.info("")
    
    results = analyzer.analyze_batch(
        df['text'].tolist(),
        df['title'].fillna('').tolist()
    )
    
    # Add results to dataframe
    df['political_score'] = [r['score'] for r in results]
    df['political_confidence'] = [r['confidence'] for r in results]
    df['political_label'] = [r['label'] for r in results]
    
    # Add dimension scores
    df['nationalism_score'] = [r['dimensions'].get('nationalism', 0) for r in results]
    df['social_values_score'] = [r['dimensions'].get('social_values', 0) for r in results]
    df['economics_score'] = [r['dimensions'].get('economics', 0) for r in results]
    
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
    
    # Overall score statistics
    logging.info(f"\nOverall Political Score Statistics:")
    logging.info(f"  Mean:   {df['political_score'].mean():+.3f}")
    logging.info(f"  Median: {df['political_score'].median():+.3f}")
    logging.info(f"  Std:    {df['political_score'].std():.3f}")
    logging.info(f"  Min:    {df['political_score'].min():+.3f}")
    logging.info(f"  Max:    {df['political_score'].max():+.3f}")
    
    # Dimension statistics
    logging.info(f"\nDimension Scores (Mean):")
    logging.info(f"  Nationalism:    {df['nationalism_score'].mean():+.3f}")
    logging.info(f"  Social Values:  {df['social_values_score'].mean():+.3f}")
    logging.info(f"  Economics:      {df['economics_score'].mean():+.3f}")
    
    # Confidence statistics
    logging.info(f"\nConfidence Statistics:")
    logging.info(f"  Mean:   {df['political_confidence'].mean():.3f}")
    logging.info(f"  Median: {df['political_confidence'].median():.3f}")
    
    # Show sample results
    logging.info(f"\nSample Results (Top 5 Conservative):")
    top_conservative = df.nlargest(5, 'political_score')[
        ['title', 'political_score', 'nationalism_score', 'social_values_score', 'economics_score']
    ]
    for _, row in top_conservative.iterrows():
        logging.info(f"  [{row['political_score']:+.2f}] {row['title'][:50]}...")
        logging.info(f"       (N:{row['nationalism_score']:+.2f} S:{row['social_values_score']:+.2f} E:{row['economics_score']:+.2f})")
    
    logging.info(f"\nSample Results (Top 5 Progressive):")
    top_progressive = df.nsmallest(5, 'political_score')[
        ['title', 'political_score', 'nationalism_score', 'social_values_score', 'economics_score']
    ]
    for _, row in top_progressive.iterrows():
        logging.info(f"  [{row['political_score']:+.2f}] {row['title'][:50]}...")
        logging.info(f"       (N:{row['nationalism_score']:+.2f} S:{row['social_values_score']:+.2f} E:{row['economics_score']:+.2f})")
    
    # Save results
    if output_path:
        logging.info(f"\n💾 Saving results to: {output_path}")
        
        output_path = Path(output_path)
        if output_path.suffix == '.csv':
            df.to_csv(output_path, index=False)
        elif output_path.suffix == '.feather':
            df.to_feather(output_path)
        elif output_path.suffix in ['.xlsx', '.xls']:
            df.to_excel(output_path, index=False)
        else:
            df.to_csv(output_path.with_suffix('.csv'), index=False)
        
        logging.info(f"   ✅ Saved {len(df):,} articles")
    else:
        # Update database
        logging.info(f"\n💾 Updating database with political scores...")
        
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(Articles)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        
        # Add columns if they don't exist
        new_columns = {
            'political_score': 'REAL',
            'political_confidence': 'REAL',
            'political_label': 'TEXT',
            'nationalism_score': 'REAL',
            'social_values_score': 'REAL',
            'economics_score': 'REAL'
        }
        
        for col_name, col_type in new_columns.items():
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE Articles ADD COLUMN {col_name} {col_type}")
        
        # Update rows
        for _, row in tqdm(df.iterrows(), total=len(df), desc="Updating database"):
            cursor.execute("""
                UPDATE Articles 
                SET political_score = ?,
                    political_confidence = ?,
                    political_label = ?,
                    nationalism_score = ?,
                    social_values_score = ?,
                    economics_score = ?
                WHERE id = ?
            """, (
                row['political_score'], 
                row['political_confidence'],
                row['political_label'],
                row['nationalism_score'],
                row['social_values_score'],
                row['economics_score'],
                row['id']
            ))
        
        conn.commit()
        logging.info(f"   ✅ Updated {len(df):,} articles in database")
    
    conn.close()
    
    logging.info("")
    logging.info("✅ Analysis complete!")
    logging.info("=" * 70)


def main():
    parser = ArgumentParser(description="Enhanced political sentiment analysis for French news articles.")
    parser.add_argument("db_path", type=str, help="Path to SQLite database")
    parser.add_argument("--output", type=str, default=None,
                       help="Output file (CSV/Excel/Feather). If not specified, updates database in-place.")
    parser.add_argument("--limit", type=int, default=None,
                       help="Limit number of articles to process (for testing)")
    parser.add_argument("--batch-size", type=int, default=4,
                       help="Batch size for processing (default: 4, keep low for zero-shot)")
    
    args = parser.parse_args()
    
    process_database(
        db_path=args.db_path,
        output_path=args.output,
        limit=args.limit,
        batch_size=args.batch_size
    )


if __name__ == "__main__":
    main()