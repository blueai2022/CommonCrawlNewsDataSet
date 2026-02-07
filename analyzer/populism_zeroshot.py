#!/usr/bin/env python3
# filepath: /workspaces/CommonCrawlNewsDataSet/analyzer/populism_zeroshot.py
# -*- coding: utf-8 -*-
"""
Populism Dimension Analysis using Zero-Shot Classification

Scores articles on three populism dimensions:
1. Anti-establishment vs. Pro-establishment (+1 to -1)
2. Economic nationalism vs. Globalism (+1 to -1)
3. People-centric vs. Technocratic (+1 to -1)

Combined score creates a populism intensity index.
"""

import sqlite3
import pandas as pd
import numpy as np
from transformers import pipeline
from tqdm import tqdm
import logging
import json
from datetime import datetime
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ============================================================================
# DIMENSION DEFINITIONS
# ============================================================================

POPULISM_DIMENSIONS = {
    'anti_establishment': {
        'positive_labels': [  # +1: Anti-establishment
            "This article criticizes the establishment, corrupt institutions, or the deep state",
            "This article expresses distrust of established political institutions",
            "This article portrays mainstream institutions as corrupt or illegitimate",
            "This article attacks political elites or the ruling class"
        ],
        'negative_labels': [  # -1: Pro-establishment
            "This article defends established institutions and their legitimacy",
            "This article expresses trust in mainstream political institutions",
            "This article portrays government institutions as effective and trustworthy",
            "This article supports the political establishment"
        ],
        'neutral_label': "This article is neutral about political institutions"
    },
    
    'economic_nationalism': {
        'positive_labels': [  # +1: Economic nationalism
            "This article advocates for protecting our economy and jobs from unfair trade",
            "This article emphasizes job protection and economic sovereignty",
            "This article criticizes trade policies as unfair to domestic workers",
            "This article opposes globalization and free trade agreements"
        ],
        'negative_labels': [  # -1: Globalism/Free trade
            "This article supports free trade and international economic cooperation",
            "This article emphasizes benefits of globalization",
            "This article advocates for open markets and trade agreements",
            "This article views international trade as beneficial"
        ],
        'neutral_label': "This article is neutral about trade and economic policy"
    },
    
    'people_centrism': {
        'positive_labels': [  # +1: People-centric/populist
            "This article appeals to the common man, the will of the people, or the silent majority",
            "This article frames issues as ordinary citizens versus elites",
            "This article claims to speak for overlooked or silenced populations",
            "This article emphasizes the wisdom of ordinary people over experts"
        ],
        'negative_labels': [  # -1: Technocratic/expert-driven
            "This article emphasizes expert knowledge and technocratic solutions",
            "This article defers to specialists and established authorities",
            "This article prioritizes evidence-based policy over popular opinion",
            "This article values institutional expertise over popular sentiment"
        ],
        'neutral_label': "This article does not take a stance on popular vs. expert authority"
    }
}

# Multilingual translations for French
DIMENSION_TRANSLATIONS = {
    'fr': {
        'anti_establishment': {
            'positive_labels': [
                "Cet article critique l'establishment, les institutions corrompues ou l'État profond",
                "Cet article exprime de la méfiance envers les institutions politiques établies",
                "Cet article dépeint les institutions comme corrompues ou illégitimes",
                "Cet article attaque les élites politiques ou la classe dirigeante"
            ],
            'negative_labels': [
                "Cet article défend les institutions établies et leur légitimité",
                "Cet article exprime sa confiance dans les institutions politiques",
                "Cet article présente les institutions gouvernementales comme efficaces",
                "Cet article soutient l'establishment politique"
            ],
            'neutral_label': "Cet article est neutre concernant les institutions politiques"
        },
        'economic_nationalism': {
            'positive_labels': [
                "Cet article plaide pour protéger notre économie et nos emplois",
                "Cet article met l'accent sur la protection de l'emploi et la souveraineté économique",
                "Cet article critique les politiques commerciales comme injustes pour les travailleurs",
                "Cet article s'oppose à la mondialisation et aux accords de libre-échange"
            ],
            'negative_labels': [
                "Cet article soutient le libre-échange et la coopération économique internationale",
                "Cet article souligne les avantages de la mondialisation",
                "Cet article défend les marchés ouverts et les accords commerciaux",
                "Cet article considère le commerce international comme bénéfique"
            ],
            'neutral_label': "Cet article est neutre sur le commerce et la politique économique"
        },
        'people_centrism': {
            'positive_labels': [
                "Cet article fait appel au peuple, à la volonté populaire ou à la majorité silencieuse",
                "Cet article oppose les citoyens ordinaires aux élites",
                "Cet article prétend parler au nom des populations négligées",
                "Cet article valorise la sagesse du peuple sur celle des experts"
            ],
            'negative_labels': [
                "Cet article met l'accent sur l'expertise et les solutions technocratiques",
                "Cet article s'en remet aux spécialistes et aux autorités établies",
                "Cet article privilégie les politiques fondées sur des preuves",
                "Cet article valorise l'expertise institutionnelle"
            ],
            'neutral_label': "Cet article ne prend pas position sur l'autorité populaire vs. experte"
        }
    }
}


class PopulismZeroShotAnalyzer:
    """Analyze populism dimensions using zero-shot classification."""
    
    def __init__(self, model_name='MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7', device=-1):
        """
        Initialize the analyzer.
        
        Args:
            model_name: Hugging Face model for zero-shot classification
            device: -1 for CPU, 0+ for GPU
        """
        logging.info(f"Loading zero-shot classifier: {model_name}")
        self.classifier = pipeline(
            "zero-shot-classification",
            model=model_name,
            device=device
        )
        self.model_name = model_name
        
    def get_labels_for_language(self, dimension: str, language: str = 'fr') -> dict:
        """Get dimension labels in the appropriate language."""
        if language in DIMENSION_TRANSLATIONS:
            return DIMENSION_TRANSLATIONS[language].get(
                dimension, 
                POPULISM_DIMENSIONS[dimension]
            )
        return POPULISM_DIMENSIONS[dimension]
    
    def score_dimension(self, text: str, dimension: str, language: str = 'fr') -> dict:
        """
        Score a single dimension for an article using chunking strategy.
        
        Strategy: Split article into chunks, score each, then aggregate.
        This captures the full article content while respecting model limits.
        
        Returns:
            dict with:
                - score: float from -1 to +1
                - positive_prob: probability of positive pole
                - negative_prob: probability of negative pole
                - neutral_prob: probability of neutral
                - confidence: max probability (indicates certainty)
                - num_chunks: number of chunks processed
        """
        labels_config = self.get_labels_for_language(dimension, language)
        
        all_labels = (
            labels_config['positive_labels'] + 
            labels_config['negative_labels'] + 
            [labels_config['neutral_label']]
        )
        
        # Split text into chunks
        # 512 tokens ≈ 350-400 words for French
        # Use word-based chunking (more reliable than character-based)
        words = text.split()
        chunk_size_words = 350  # Safe margin under 512 token limit
        
        chunks = []
        
        if len(words) <= chunk_size_words:
            # Short article: use entire text
            chunks = [text]
        else:
            # Long article: extract beginning (40%), middle (30%), end (30%)
            total_words = len(words)
            
            # Chunk 1: First 40% (introduction, headline context)
            chunk1_end = min(chunk_size_words, int(total_words * 0.4))
            chunks.append(' '.join(words[:chunk1_end]))
            
            # Chunk 2: Middle 30% (main content)
            chunk2_start = int(total_words * 0.35)  # Start at 35% to overlap
            chunk2_end = min(chunk2_start + chunk_size_words, int(total_words * 0.65))
            if chunk2_start < total_words:
                chunks.append(' '.join(words[chunk2_start:chunk2_end]))
            
            # Chunk 3: Last 30% (conclusion, summary)
            chunk3_start = max(0, total_words - chunk_size_words)
            if chunk3_start > chunk2_end:  # Avoid duplicate if article is short
                chunks.append(' '.join(words[chunk3_start:]))
        
        # Score each chunk
        chunk_results = []
        
        try:
            for chunk in chunks:
                result = self.classifier(
                    chunk,
                    candidate_labels=all_labels,
                    multi_label=True
                )
                
                label_scores = dict(zip(result['labels'], result['scores']))
                
                positive_scores = [label_scores.get(label, 0) for label in labels_config['positive_labels']]
                negative_scores = [label_scores.get(label, 0) for label in labels_config['negative_labels']]
                neutral_score = label_scores.get(labels_config['neutral_label'], 0)
                
                chunk_results.append({
                    'positive_prob': np.mean(positive_scores),
                    'negative_prob': np.mean(negative_scores),
                    'neutral_prob': neutral_score
                })
            
            # Aggregate chunk results with weights
            if len(chunk_results) == 1:
                # Only one chunk
                positive_prob = chunk_results[0]['positive_prob']
                negative_prob = chunk_results[0]['negative_prob']
                neutral_prob = chunk_results[0]['neutral_prob']
            else:
                # Multiple chunks: weighted average (40%, 30%, 30%)
                weights = [0.4, 0.3, 0.3][:len(chunk_results)]
                # Normalize weights if we have fewer chunks
                weights = np.array(weights) / sum(weights)
                
                positive_prob = sum(w * r['positive_prob'] for w, r in zip(weights, chunk_results))
                negative_prob = sum(w * r['negative_prob'] for w, r in zip(weights, chunk_results))
                neutral_prob = sum(w * r['neutral_prob'] for w, r in zip(weights, chunk_results))
            
            # Normalize probabilities
            total = positive_prob + negative_prob + neutral_prob
            if total > 0:
                positive_prob /= total
                negative_prob /= total
                neutral_prob /= total
            
            # Calculate final score: +1 (positive) to -1 (negative)
            score = positive_prob - negative_prob
            confidence = max(positive_prob, negative_prob, neutral_prob)
            
            return {
                'score': round(score, 4),
                'positive_prob': round(positive_prob, 4),
                'negative_prob': round(negative_prob, 4),
                'neutral_prob': round(neutral_prob, 4),
                'confidence': round(confidence, 4),
                'num_chunks': len(chunks)
            }
            
        except Exception as e:
            logging.error(f"Error scoring dimension {dimension}: {e}")
            return {
                'score': 0.0,
                'positive_prob': 0.0,
                'negative_prob': 0.0,
                'neutral_prob': 1.0,
                'confidence': 0.0,
                'num_chunks': 0
            }
    
    def analyze_article(self, text: str, language: str = 'en') -> dict:
        """
        Analyze all populism dimensions for an article.
        
        Returns:
            dict with scores for each dimension plus composite score
        """
        results = {}
        
        for dimension in POPULISM_DIMENSIONS.keys():
            dim_result = self.score_dimension(text, dimension, language)
            results[dimension] = dim_result
        
        # Calculate composite populism score
        dimension_scores = [results[dim]['score'] for dim in POPULISM_DIMENSIONS.keys()]
        results['composite'] = {
            'score': round(np.mean(dimension_scores), 4),
            'confidence': round(np.mean([results[dim]['confidence'] for dim in POPULISM_DIMENSIONS.keys()]), 4)
        }
        
        return results


def process_database(db_path: str, 
                     output_csv: str = 'populism_zeroshot_scores.csv',
                     model_name: str = 'MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7',
                     sample_size: int = None,
                     batch_size: int = 100,
                     country_filter: str = 'FR'):  # NEW PARAMETER
    """
    Process articles from database and score populism dimensions.
    
    Args:
        country_filter: NUTS country code to filter (e.g., 'FR' for France)
    """
    logging.info("=" * 70)
    logging.info("🗳️  Populism Zero-Shot Classification")
    logging.info("=" * 70)
    
    # Initialize analyzer
    analyzer = PopulismZeroShotAnalyzer(model_name=model_name)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    
    # Build query with country filter
    query = """
        SELECT 
            a.id, a.title, a.text, a.date,
            l.NUTS as nuts_code
        FROM Articles a
        INNER JOIN Article_Locations al ON a.id = al.article_id
        INNER JOIN Locations l ON al.location_id = l.location_id
        WHERE a.text IS NOT NULL 
          AND LENGTH(a.text) > 300
          AND l.NUTS IS NOT NULL
    """
    
    # Add country filter
    if country_filter:
        query += f" AND l.NUTS LIKE '{country_filter}%'"
        logging.info(f"   Filtering for country: {country_filter}")
    
    if sample_size:
        query += f" ORDER BY RANDOM() LIMIT {sample_size}"
    
    logging.info("📖 Loading articles from database...")
    articles = pd.read_sql(query, conn)
    conn.close()
    
    # All articles are French (since we filtered for FR)
    articles['language'] = 'fr'
    
    logging.info(f"   Loaded {len(articles):,} articles")
    logging.info(f"   Language: French")
    
    if len(articles) == 0:
        logging.error("❌ No articles found! Check your database.")
        return None, None
    
    # Process articles
    logging.info("\n🔍 Analyzing populism dimensions...")
    results = []
    
    for i, row in tqdm(articles.iterrows(), total=len(articles), desc="Processing"):
        # Analyze article - will use French labels
        analysis = analyzer.analyze_article(row['text'], row['language'])
        
        # Flatten results
        result = {
            'article_id': row['id'],
            'nuts_code': row['nuts_code'],
            'nuts2': row['nuts_code'][:4] if row['nuts_code'] and len(row['nuts_code']) >= 4 else None,
            'date': row['date'],
            'year': pd.to_datetime(row['date']).year if row['date'] else None,
            'language': row['language'],
            
            # Anti-establishment dimension
            'anti_estab_score': analysis['anti_establishment']['score'],
            'anti_estab_pos_prob': analysis['anti_establishment']['positive_prob'],
            'anti_estab_neg_prob': analysis['anti_establishment']['negative_prob'],
            'anti_estab_confidence': analysis['anti_establishment']['confidence'],
            
            # Economic nationalism dimension
            'econ_nat_score': analysis['economic_nationalism']['score'],
            'econ_nat_pos_prob': analysis['economic_nationalism']['positive_prob'],
            'econ_nat_neg_prob': analysis['economic_nationalism']['negative_prob'],
            'econ_nat_confidence': analysis['economic_nationalism']['confidence'],
            
            # People-centrism dimension
            'people_centric_score': analysis['people_centrism']['score'],
            'people_centric_pos_prob': analysis['people_centrism']['positive_prob'],
            'people_centric_neg_prob': analysis['people_centrism']['negative_prob'],
            'people_centric_confidence': analysis['people_centrism']['confidence'],
            
            # Composite score
            'populism_composite': analysis['composite']['score'],
            'composite_confidence': analysis['composite']['confidence']
        }
        
        results.append(result)
        
        # Save progress periodically
        if (i + 1) % batch_size == 0:
            logging.info(f"   Processed {i+1:,} articles...")
            pd.DataFrame(results).to_csv(output_csv.replace('.csv', '_progress.csv'), index=False)
    
    # Create results DataFrame
    results_df = pd.DataFrame(results)
    
    # Save article-level results
    results_df.to_csv(output_csv.replace('.csv', '_articles.csv'), index=False)
    logging.info(f"\n💾 Saved article-level results to: {output_csv.replace('.csv', '_articles.csv')}")
    
    # Aggregate to NUTS2-year level
    logging.info("\n📊 Aggregating to NUTS2-year level...")
    
    regional = results_df.groupby(['nuts2', 'year']).agg({
        'anti_estab_score': ['mean', 'std'],
        'econ_nat_score': ['mean', 'std'],
        'people_centric_score': ['mean', 'std'],
        'populism_composite': ['mean', 'std'],
        'composite_confidence': 'mean',
        'article_id': 'count'
    }).reset_index()
    
    # Flatten column names
    regional.columns = [
        'nuts2', 'year',
        'anti_estab_mean', 'anti_estab_sd',
        'econ_nat_mean', 'econ_nat_sd',
        'people_centric_mean', 'people_centric_sd',
        'populism_mean', 'populism_sd',
        'confidence_mean', 'article_count'
    ]
    
    # Save regional results
    regional.to_csv(output_csv, index=False)
    
    # Print summary
    logging.info(f"\n✅ Saved regional results to: {output_csv}")
    logging.info(f"   Regions: {regional['nuts2'].nunique()}")
    logging.info(f"   Years: {regional['year'].min()}-{regional['year'].max()}")
    logging.info(f"   Total articles: {regional['article_count'].sum():,}")
    
    return results_df, regional


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python populism_zeroshot.py <db_path> [output.csv] [--sample N] [--country XX]")
        sys.exit(1)
    
    db_path = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else 'populism_zeroshot_scores.csv'
    
    # Check for sample flag
    sample_size = None
    if '--sample' in sys.argv:
        idx = sys.argv.index('--sample')
        sample_size = int(sys.argv[idx + 1])
    
    # Check for country filter
    country_filter = 'FR'  # Default to France
    if '--country' in sys.argv:
        idx = sys.argv.index('--country')
        country_filter = sys.argv[idx + 1]
    
    # Run analysis
    results_df, regional = process_database(
        db_path=db_path,
        output_csv=output,
        sample_size=sample_size,
        country_filter=country_filter
    )