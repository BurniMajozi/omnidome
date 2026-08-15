@echo off
setlocal

cd /d "C:\Users\Benedict\Desktop\OminiDome\omnidome\apps\customer-app\android"
.\gradlew assembleDebug --console=plain
echo BUILD_EXIT_CODE: %errorlevel%