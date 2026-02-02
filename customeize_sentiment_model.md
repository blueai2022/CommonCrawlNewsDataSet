1. **Zero-shot Classification**: Uses NLI (Natural Language Inference) models that can understand political concepts without being explicitly trained on them

2. **Multi-dimensional Analysis**: Breaks down politics into 3 dimensions:
   - **Nationalism** (40% weight): Immigration, sovereignty, national identity
   - **Social Values** (30% weight): Traditional vs. progressive values
   - **Economics** (30% weight): Free market vs. redistribution

3. **Fine-grained Labels**: Instead of simple keywords, uses descriptive phrases like:
   - Conservative: "défense de la souveraineté nationale", "valeurs traditionnelles"
   - Progressive: "ouverture aux réfugiés", "égalité des genres"

4. **Multi-label Scoring**: Each text is scored against ALL labels simultaneously, capturing nuance

5. **Confidence Weighting**: Model provides confidence scores for each prediction

**Performance note:**
- Much slower than keyword-based (100-500 articles/hour vs 1000s/hour)
- But significantly more accurate
- Use `--limit 100` for testing first

**Usage:**
```bash
# Test with 50 articles
python 11_political_sentiment_analysis.py /data/CommonCrawl/news/news_database.db --limit 50 --output test.csv

# Full run (will take hours)
python 11_political_sentiment_analysis.py /data/CommonCrawl/news/news_database.db
```
