#!/system/bin/sh
MODDIR=${0%/*}
# A clean boot allows another attempt next time; interrupted boots fail safe.
rm -f "$MODDIR/boot-pending"
