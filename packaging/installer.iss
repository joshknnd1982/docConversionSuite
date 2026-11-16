; Inno Setup script for Document Conversion Suite (built on the pdfmd engine).
;
; The installer wizard uses only standard Windows controls (buttons, check
; boxes, radio buttons, edit fields, progress bar), so NVDA, JAWS and
; Narrator read every page, and it can be completed with the keyboard
; alone: Tab and Shift+Tab move between controls, Space toggles check boxes,
; Alt+N goes to the next page, Alt+B goes back and Enter activates the
; default button.
;
; Build with:  python packaging/build.py
; (it passes AppVersion, SourceDir, DocsDir and OutputDir with /D).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\DocConversionSuite"
#endif
#ifndef DocsDir
  #define DocsDir "build\docs"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif

#define AppName "Document Conversion Suite"
#define AppExe "DocConversionSuite.exe"
#define AppPublisher "Josh Kennedy"
#define AppURL "https://github.com/joshknnd1982/docConversionSuite"

[Setup]
AppId={{C339688A-B79D-4356-8542-16C1BDDD3988}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
AppComments=Accessible document converter: PDF to Markdown, accessible math, and every pandoc format
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Install for the current user by default (no administrator prompt). The
; wizard offers "install for all users" as a choice.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename=DocConversionSuite-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExe}
ChangesAssociations=yes
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} installer
ShowLanguageDialog=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "contextmenu"; Description: "Add ""Convert with Document Conversion Suite"" to the right-click menu (and Applications key menu) of PDF files"; GroupDescription: "Explorer integration:"
Name: "installtesseract"; Description: "Install Tesseract OCR with winget, so scanned PDFs become accessible text (needs internet)"; GroupDescription: "Optional components:"
Name: "installpandoc"; Description: "Install Pandoc with winget, for Word, EPUB, HTML, LaTeX and every other pandoc format (needs internet)"; GroupDescription: "Optional components:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\ACCESSIBILITY.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\FEATURES.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}\docs"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "{#DocsDir}\*.html"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Convert PDFs and documents to accessible Markdown, HTML, Word, EPUB and more"
Name: "{group}\Accessibility Guide"; Filename: "{app}\docs\ACCESSIBILITY.html"; Comment: "Accessibility features and keyboard shortcuts"
Name: "{group}\Features Guide"; Filename: "{app}\docs\FEATURES.html"; Comment: "Everything Document Conversion Suite can do"
Name: "{group}\Command Prompt for pdfmd-cli"; Filename: "{cmd}"; Parameters: "/k ""cd /d ""{app}"" && pdfmd-cli --help"""; WorkingDir: "{app}"; Comment: "Command prompt for the pdfmd-cli command-line converter"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; "Convert with Document Conversion Suite" on PDF files (Explorer context
; menu, also reached with the Applications key or Shift+F10).
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu

[Run]
Filename: "{cmd}"; Parameters: "/c winget install --id UB-Mannheim.TesseractOCR --exact --source winget & echo. & echo Press any key to continue setup. & pause >nul"; StatusMsg: "Installing Tesseract OCR with winget..."; Flags: waituntilterminated; Tasks: installtesseract
Filename: "{cmd}"; Parameters: "/c winget install --id JohnMacFarlane.Pandoc --exact --source winget & echo. & echo Press any key to continue setup. & pause >nul"; StatusMsg: "Installing Pandoc with winget..."; Flags: waituntilterminated; Tasks: installpandoc
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent
Filename: "{app}\docs\ACCESSIBILITY.html"; Description: "Open the accessibility guide"; Flags: postinstall shellexec skipifsilent unchecked
