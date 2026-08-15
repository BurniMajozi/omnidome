@echo off
setlocal

set ANDROID_HOME=C:\Users\Benedict\AppData\Local\Android\Sdk
set ANDROID_SDK_ROOT=%ANDROID_HOME%
set JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-17.0.19.8-hotspot

cd /d "C:\Users\Benedict\Desktop\OminiDome\omnidome\apps\customer-app\android"

gradle assembleDebug --console=plain

echo BUILD_EXIT_CODE:%errorlevel%
