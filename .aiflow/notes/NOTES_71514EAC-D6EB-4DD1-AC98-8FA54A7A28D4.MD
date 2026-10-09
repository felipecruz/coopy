# F9 snapshot recovery

F9 is complete. All 114 tests passed on Python 3.12.2/macOS, including failure recovery and F7 restart cases. No setup or data migration is required.

## After a failed snapshot

Keep the previous numbered checkpoint and every later-numbered journal. A failed attempt may rotate the journal without publishing a checkpoint; those journals are still required for recovery.

Recovery ignores hidden `.coopy-snapshot-*` files left by interruption or failed cleanup. If you need to remove them, stop the persistent system first. Cleanup failures are logged, while the original snapshot error reaches the caller.

## Validation limits

Run the supported Python/OS CI matrix before release. This change does not guarantee power-loss durability or repair pre-existing corrupted checkpoints.
