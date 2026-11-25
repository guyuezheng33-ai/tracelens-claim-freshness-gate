# One-command verification on Windows (no make / Git Bash required).
# POSIX equivalent: make verify
& "$PSScriptRoot\scripts\award-verify.ps1" @args
exit $LASTEXITCODE