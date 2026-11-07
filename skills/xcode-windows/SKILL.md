---
name: xcode-windows
description: Keep Xcode's windows stable while working in an iOS or macOS project. Use before opening, building, running, or testing a project — never open .xcodeproj or .xcworkspace documents, build with the xcodebuild CLI instead.
---

# Xcode windows

Xcode's open documents belong to the user. Do not change them.

## Rules

- **Never open an Xcode document.** Do not run `open -a Xcode`, `xed`, or
  `open -b com.apple.dt.Xcode` on a `.xcodeproj` or `.xcworkspace`, and do not
  launch Xcode at all to work on the project.
- **Never open a second document.** If Xcode already has a project or workspace
  open, opening another copy — or the same project through its workspace — shows
  "Couldn't load ... because it is already opened from another project or
  workspace". Do not close or reopen the user's windows to work around it.
- **Build with the CLI.** Use `xcodebuild -workspace <name>.xcworkspace -scheme
  <scheme> ...`, `xcodebuild -project ...`, `xcodebuild test`, and `xcrun
  simctl` for simulators. The CLI leaves Xcode's windows untouched and reports
  errors in its own output.
- **Prefer the workspace.** When a project has both, the `.xcworkspace` is the
  entry point (with CocoaPods it includes the pod targets). Never switch the
  user from the workspace to the bare `.xcodeproj`.
- **Ask before opening.** If opening a document is truly unavoidable, ask the
  user first, explain why, and let them open it.
- **Leave dialogs and windows alone.** Do not drive Xcode's UI with AppleScript
  or System Events unless the user explicitly asks you to.

## When the conflict appears

If Xcode reports that a document is already opened from another project or
workspace, tell the user to dismiss it. Continue with the CLI; do not try to
fix it by opening or closing documents.
