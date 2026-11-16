; Inno Setup script for Document Conversion Suite (built on the pdfmd engine).
;
; The installer wizard uses only standard Windows controls (buttons, check
; boxes, radio buttons, edit fields, progress bar), so NVDA, JAWS and
; Narrator read every page, and it can be completed with the keyboard
; alone: Tab and Shift+Tab move between controls, Space toggles check boxes,
; Alt+N goes to the next page, Alt+B goes back and Enter activates the
; default button.
;
; Pandoc, Tesseract OCR (with 17 OCR languages) and the picture-description
; vision model (llama.cpp engine + Qwen3-VL 2B abliterated) are bundled in
; the program folder, so everything works offline right after installing.
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
AppComments=Accessible document converter with built-in pandoc, Tesseract OCR and a local AI vision model
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
Name: "contextmenu"; Description: "Add ""Convert with Document Conversion Suite"" to the right-click menu (and Applications key menu) of documents and folders"; GroupDescription: "Explorer integration:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "*.gguf"; Flags: ignoreversion recursesubdirs createallsubdirs
; The vision model files are already compressed; storing them as they are
; keeps the build fast and the installer the same size.
Source: "{#SourceDir}\vision\models\*"; DestDir: "{app}\vision\models"; Flags: ignoreversion recursesubdirs createallsubdirs nocompression
Source: "..\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\ACCESSIBILITY.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\FEATURES.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}\docs"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "THIRD-PARTY-NOTICES.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#DocsDir}\*.html"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Convert PDFs and documents to accessible Markdown, HTML, Word, EPUB and more, with pictures described"
Name: "{group}\Accessibility Guide"; Filename: "{app}\docs\ACCESSIBILITY.html"; Comment: "Accessibility features and keyboard shortcuts"
Name: "{group}\Features Guide"; Filename: "{app}\docs\FEATURES.html"; Comment: "Everything Document Conversion Suite can do"
Name: "{group}\Command Prompt for pdfmd-cli"; Filename: "{cmd}"; Parameters: "/k ""cd /d ""{app}"" && pdfmd-cli --help"""; WorkingDir: "{app}"; Comment: "Command prompt for the pdfmd-cli command-line converter"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; "Convert with Document Conversion Suite" on documents and folders
; (Explorer context menu, also reached with the Applications key or Shift+F10).
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.docx\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.odt\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rtf\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.epub\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.epub\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.epub\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.html\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.html\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.html\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.htm\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.htm\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.htm\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.md\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.markdown\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.markdown\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.markdown\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pptx\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tex\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tex\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.tex\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rst\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rst\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.rst\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.adoc\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.adoc\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.adoc\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.org\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.org\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.org\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ipynb\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ipynb\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.ipynb\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.typ\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.typ\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.typ\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.fb2\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.fb2\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.fb2\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\DocConversionSuite"; ValueType: string; ValueName: ""; ValueData: "Convert with {#AppName}"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\DocConversionSuite"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\DocConversionSuite\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent
Filename: "{app}\docs\ACCESSIBILITY.html"; Description: "Open the accessibility guide"; Flags: postinstall shellexec skipifsilent unchecked
