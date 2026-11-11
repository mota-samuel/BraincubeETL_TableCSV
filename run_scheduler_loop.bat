@echo off
cd /d C:\Users\samuel_mota\Documents\BrainCube_ETL
call .venv\Scripts\activate.bat
python -m src.scheduler --loop --interval 60
pausegi