[app]

# pyside6-deploy configuration file for building DCMspec Explorer as a native app.
# Build with: poetry run build-app
# It builds from a copy in build/, because the tool rewrites the spec it is given.
# Nuitka, a Python-to-C compiler, is installed into the venv by the tool.

# Name of the output folder, applied after the build; not passed to Nuitka
title = dcmspec-explorer
project_dir = ../src/dcmspec_explorer
input_file = src/dcmspec_explorer/main.py
exec_directory = build
project_file = 
icon = 

[python]
python_path = 
packages = Nuitka==4.2.2
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]
qml_files = 
excluded_qml_plugins = 
modules = Core,DBus,Gui,Widgets
plugins = accessiblebridge,egldeviceintegrations,generic,iconengines,imageformats,platforminputcontexts,platforms,platforms/darwin,platformthemes,styles,wayland-decoration-client,wayland-graphics-integration-client,wayland-shell-integration,xcbglintegrations

[nuitka]
macos.permissions = 
mode = onefile

# --quiet = less Nuitka output
# --static-libpython = no: Nuitka's static libpython detection fails with Homebrew Python
# --noinclude-qt-translations = smaller bundle
# --include-data-dir = resources are not bundled by default; destination must match importlib.resources
# --macos-create-app-bundle = produce a .app on macOS (ignored elsewhere)
# --macos-app-name = menu bar name (may have a space); otherwise Info.plist identity is "main"
# --output-filename = name of the inner executable; otherwise "main" (checked on macOS only)
extra_args = 
	--quiet
	--static-libpython=no
	--noinclude-qt-translations
	--include-data-dir=src/dcmspec_explorer/resources=dcmspec_explorer/resources
	--macos-create-app-bundle
	--macos-app-name="DCMspec Explorer"
	--output-filename=dcmspec-explorer

# Android section (unused)
[buildozer]
mode = debug
recipe_dir = 
jars_dir = 
ndk_path = 
sdk_path = 
local_libs = 
arch = 

