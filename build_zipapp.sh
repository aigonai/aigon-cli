#!/bin/bash
# Build aigon CLI as a standalone zipapp (.pyz)
set -e
VERSION=$(python3 -c "exec(open('aigon_cli/version.py').read()); print(__version__)")
mkdir -p dist

# Create temp build directory with package inside it
BUILD_DIR=$(mktemp -d)
trap "rm -rf $BUILD_DIR" EXIT
cp -r aigon_cli "$BUILD_DIR/aigon_cli"
cat > "$BUILD_DIR/__main__.py" << 'EOF'
from aigon_cli.cli import main
main()
EOF

python3 -m zipapp "$BUILD_DIR" -p "/usr/bin/env python3" -o "dist/aigon.pyz"
echo "Built dist/aigon.pyz (v${VERSION})"
