from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def show_symlink_permission_dialog(parent: QWidget) -> str:
    """Shown the first time a symlink creation fails due to missing
    Windows privileges. Returns "abort" or "skip" -- never silently
    substitutes a hardlink/copy, per the product requirement that link
    failures must be surfaced, not papered over.
    """
    box = QMessageBox(parent)
    box.setWindowTitle("Can't create category-folder links")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(
        "Windows requires either running as Administrator or enabling "
        "Developer Mode to create the category-folder shortcuts (symlinks) "
        "this app uses.\n\n"
        "To enable Developer Mode: Settings > Privacy & security > For "
        "developers > Developer Mode.\n\n"
        "You can stop now and retry after enabling it, or continue this "
        "run without category-folder links (files will still be sorted, "
        "renamed, and get an NFO + cover)."
    )
    abort_button = box.addButton("Stop this run", QMessageBox.ButtonRole.RejectRole)
    skip_button = box.addButton("Continue without links", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(skip_button)
    box.exec()
    return "abort" if box.clickedButton() is abort_button else "skip"
