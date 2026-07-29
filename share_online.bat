@echo off
chcp 65001 > nul
title إنشاء رابط عام للموقع (Share Online)
cls
echo ===================================================================
echo             🌐 جاري توليد رابط عالمي لمشاركة الموقع
echo ===================================================================
echo.
echo  سيتم إنشاء رابط أونلاين يمكنك إرساله عبر WhatsApp أو Telegram.
echo  تأكد أنك قمت بتشغيل start_server.bat أولاً!
echo.
echo ===================================================================
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -R 80:127.0.0.1:8000 serveo.net
pause
