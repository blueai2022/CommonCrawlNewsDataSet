
python3 -m venv venv

source venv/bin/activate

pip install 'pandas>=2.0.0'
pip install 'openpyxl>=3.1.0'

mkdir -p ./dump

python3 ./dump_db_to_csv.py ./news_database_01.db ./dump


cd dump/
ls -l

head -10 Articles.csv

wc -l Articles.csv
wc -l articles_with_locations.csv 
