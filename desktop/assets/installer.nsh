; Custom NSIS hooks for electron-builder (nsis.include in electron-builder.yml).

; On a real uninstall (not the one an update runs), offer to delete the user's
; data: the SQLite database, downloaded FITS/images, analysis sessions, logs and
; settings. Default is to keep it, so reinstalling picks up where it left off.
!macro customUnInstall
  ${ifNot} ${isUpdated}
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 \
      "Also delete the dashboard's local data (database, downloaded files, logs and settings)?$\r$\n$\r$\n$LOCALAPPDATA\SolarDashboard" \
      /SD IDNO IDNO keepUserData
      RMDir /r "$LOCALAPPDATA\SolarDashboard"
    keepUserData:
  ${endIf}
!macroend
