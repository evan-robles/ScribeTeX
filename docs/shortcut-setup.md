# iPad Shortcut Setup

This guide walks you through creating an iPad Shortcut that sends notes from GoodNotes (or any app) directly to your ScribeTeX inbox with one tap.

## Recipe

### 1. Create a new Shortcut (iPad)

Open the **Shortcuts** app on your iPad and tap **Create Shortcut**. You now have a blank canvas.

### 2. Enable "Show in Share Sheet"

- Tap the three-dot menu (⋯) at the top right.
- Select **Settings** or look for Shortcut Settings.
- Enable **"Show in Share Sheet"**.
- Under **Accepted Types**, select **Images**, **PDFs**, and **Files**.

This allows you to invoke the shortcut from the Share Sheet in any app.

### 3. Add a "Save File" action

- Tap the **+** button to add an action.
- Search for and select **"Save File"**.
- Set the **destination folder** to the exact cloud folder that your Mac ScribeTeX app watches as its inbox.
  - This is the same folder you configured in the Mac menu-bar app settings.
  - Common options: iCloud Drive, Google Drive, Dropbox, Box, or a custom `ScribeTeX-Inbox` folder.
- **Turn OFF** "Ask Where to Save" — you want the file to go directly to the inbox, no prompts.

### 4. Name the Shortcut

- Tap **Done** or the **back** button.
- Name the shortcut **"ScribeTeX"**.
- Save it.

### 5. Use it from GoodNotes

- In **GoodNotes**, open or create a note.
- Tap **Share** (or the export/send icon).
- Select **"ScribeTeX"** from the list of shortcuts.
- The PDF is saved instantly to your inbox folder.
- Your Mac app watches the folder and picks up the file within seconds. It will transcribe, place, and file the note automatically.

## Important Notes

- **Destination folder must match.** The folder you set in Step 3 must be the exact same cloud folder your Mac menu-bar app is watching. If you change the inbox in the Mac app settings, update the Shortcut's Save File destination to match.
- **Cloud sync required.** The folder must be synced between your iPad and Mac (iCloud Drive, Google Drive, Dropbox, etc.). Local folders will not work.
- **One tap.** After setup, sharing a note from GoodNotes to ScribeTeX is just two taps: Share → ScribeTeX.

## Troubleshooting

- **File doesn't appear on Mac.** Check that the folder path is identical in both the Shortcut and the Mac app settings.
- **Shortcut doesn't appear in Share Sheet.** Re-check that "Show in Share Sheet" is enabled in Shortcut Settings, and that you've selected the accepted types (PDFs, Files, etc.).
