@echo off
setlocal

REM Executa sempre na pasta onde o .bat esta
cd /d "%~dp0"

echo ============================================
echo Atualizacao de dados do website
echo Pasta: %CD%
echo ============================================

REM Escolher launcher Python (py preferencial, fallback python)
where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py"
) else (
  set "PY=python"
)

echo [1/4] Validar dependencia tabulate...
%PY% -m pip show tabulate >nul 2>&1
if not %errorlevel%==0 (
  echo tabulate nao encontrado. A instalar...
  %PY% -m pip install tabulate
  if errorlevel 1 (
    echo ERRO: Falha ao instalar tabulate.
    exit /b 1
  )
)

echo [2/4] Recalcular outputs com analisar_equipas.py...
%PY% analisar_equipas.py --csv-dir "." --outdir "output" --min-games 5 --lay
if errorlevel 1 (
  echo ERRO: analisar_equipas.py falhou.
  exit /b 1
)

echo [3/5] Recolher jogos futuros (API football-data)...
%PY% scripts\fetch_fixtures.py
if errorlevel 1 (
  echo ERRO: fetch_fixtures.py falhou.
  exit /b 1
)

echo [4/5] Atualizar changelog semanal...
%PY% scripts\update_changelog.py
if errorlevel 1 (
  echo ERRO: update_changelog.py falhou.
  exit /b 1
)

echo [5/5] Regenerar site/data/site-data.json...
%PY% scripts\build_site_data.py
if errorlevel 1 (
  echo ERRO: build_site_data.py falhou.
  exit /b 1
)

echo.
echo OK: Atualizacao concluida com sucesso.
echo.
echo Proximo passo para publicar na Vercel:
echo   git add .
echo   git commit -m "update dados"
echo   git push
echo.

endlocal
