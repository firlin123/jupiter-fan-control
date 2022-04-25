# Maintainer: Adam Weld <weld@valvesoftware.com>

pkgname=jupiter-fan-controller
pkgver=0.0.2
pkgrel=3
arch=('any')
license=('GPLv3')
depends=('python3' 'python-pyaml')
makedepends=('git' 'rsync')
# skipping sha256 sums for dev iteration - no 'makepkg -g' needed
package() {
   rsync -a --exclude 'README.md' "$srcdir"/jupiter-fan-control/* "$pkgdir"
}
sha256sums=('SKIP'
            'SKIP'
            'SKIP'
            'SKIP')
