Write-Host "======================================================================" -ForegroundColor Green
Write-Host "Starting Green Pulse Web Application..." -ForegroundColor Cyan
Write-Host "Tagline: 'Track Your Impact. Make Every Action Count.'" -ForegroundColor Gray
Write-Host "======================================================================" -ForegroundColor Green

python -m pip install -r requirements.txt --quiet
Write-Host "`nLaunching server on http://127.0.0.1:5000 ..." -ForegroundColor Yellow
Write-Host "Open your browser at http://127.0.0.1:5000" -ForegroundColor Cyan
Write-Host "(Press CTRL+C in this terminal window to stop the server)`n" -ForegroundColor Gray

python app.py
