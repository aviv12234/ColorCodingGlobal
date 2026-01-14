
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Iterable, Tuple

from aqt import mw
from aqt.qt import (
    QAction,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QCheckBox,
    QMessageBox,
    Qt,
)
from aqt.utils import showInfo, tooltip


# At top of the file with your other imports
from aqt.qt import QAbstractItemView, Qt

def _multi_select_mode():
    """Return a MultiSelection enum that works in both Qt5 and Qt6."""
    # PyQt6 preferred
    try:
        return QAbstractItemView.SelectionMode.MultiSelection  # PyQt6
    except AttributeError:
        pass
    # Fallbacks
    try:
        return Qt.SelectionMode.MultiSelection  # PyQt6 alternative
    except AttributeError:
        pass
    try:
        return QAbstractItemView.MultiSelection  # PyQt5
    except AttributeError:
        pass
    # Last resort: ExtendedSelection still allows multiple selection
    try:
        return QAbstractItemView.SelectionMode.ExtendedSelection
    except AttributeError:
        return QAbstractItemView.ExtendedSelection



# =========================
# 1) Get your color table
# =========================
# Reuse your existing color table loader if you already have one.
# Try to import from your extension; fall back to a simple config example.

def get_color_table() -> Dict[str, str]:
    """
    Load the 'normal version' ColorCoding data format from this add-on's config:
    config["color_entries"] is expected to be a list like:
    [
      {"word": "penicillin", "group": "", "color": "red"},
      {"word": "doxycycline", "group": "", "color": "green"}
    ]
    Returns a flat dict {word: color}.
    """
    try:
        cfg = mw.addonManager.getConfig(__name__) or {}
        entries = cfg.get("color_entries", [])
        if not isinstance(entries, list):
            return {}
        table: Dict[str, str] = {}
        for row in entries:
            if not isinstance(row, dict):
                continue
            w = str(row.get("word", "")).strip()
            c = str(row.get("color", "")).strip()
            if w and c:
                table[w] = c
        return table
    except Exception:
        # Fallback to empty table on any error
        return {}



def _exec_dialog(dlg) -> int:
    """Return dialog result compatibly across Qt5/Qt6."""
    # PyQt6
    try:
        result = dlg.exec()
    except AttributeError:
        # PyQt5 fallback
        result = dlg.exec_()
    return result

def _accepted_code() -> int:
    """Return the Accepted enum value compatibly across Qt5/Qt6."""
    from aqt.qt import QDialog
    try:
        return int(QDialog.DialogCode.Accepted)  # PyQt6
    except AttributeError:
        return int(QDialog.Accepted)             # PyQt5



# =========================
# 2) Deck selection dialog
# =========================
class DeckPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apply Color Coding to Selected Decks")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select one or more decks:"))

        self.deck_list = QListWidget(self)
        self.deck_list.setSelectionMode(_multi_select_mode())
        for d in sorted(deck_names_with_children_flag().keys()):
            item = QListWidgetItem(d)
            self.deck_list.addItem(item)

        layout.addWidget(self.deck_list)

        # Options
        self.include_children_cb = QCheckBox("Include subdecks", self)
        self.include_children_cb.setChecked(True)

        self.skip_cloze_cb = QCheckBox("Skip Cloze models", self)
        self.skip_cloze_cb.setChecked(True)

        self.whole_words_cb = QCheckBox("Whole words only", self)
        self.whole_words_cb.setChecked(True)

        self.case_insensitive_cb = QCheckBox("Case insensitive", self)
        self.case_insensitive_cb.setChecked(True)

        self.dry_run_cb = QCheckBox("Dry run (don’t modify—report only)", self)
        self.dry_run_cb.setChecked(False)

        for cb in [
            self.include_children_cb,
            self.skip_cloze_cb,
            self.whole_words_cb,
            self.case_insensitive_cb,
            self.dry_run_cb,
        ]:
            layout.addWidget(cb)

        # Buttons
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Run")
        self.cancel_btn = QPushButton("Cancel")
        self.run_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.run_btn)
        layout.addLayout(btn_row)

    def selected_decks(self) -> List[str]:
        return [i.text() for i in self.deck_list.selectedItems()]

    def include_children(self) -> bool:
        return self.include_children_cb.isChecked()

    def skip_cloze(self) -> bool:
        return self.skip_cloze_cb.isChecked()

    def whole_words(self) -> bool:
        return self.whole_words_cb.isChecked()

    def case_insensitive(self) -> bool:
        return self.case_insensitive_cb.isChecked()

    def dry_run(self) -> bool:
        return self.dry_run_cb.isChecked()


def deck_names_with_children_flag() -> Dict[str, bool]:
    """
    Returns deck names. The bool value isn't used here but is helpful
    if you later want to show which decks have children.
    """
    decks = mw.col.decks.all_names_and_ids()
    # all_names_and_ids -> list of (name, id) in recent Anki versions
    # Fallback if needed:
    if isinstance(decks, list) and decks and isinstance(decks[0], tuple):
        return {name: True for (name, _id) in decks}
    else:
        # Back-compat: derive names another way
        names = [d["name"] for d in mw.col.decks.all()]
        return {n: True for n in names}


# =========================
# 3) Core coloring helpers
# =========================

@dataclass
class ColoringOptions:
    whole_words: bool = True
    case_insensitive: bool = True


def build_combined_regex(color_table: Dict[str, str], opts: ColoringOptions) -> Tuple[re.Pattern, Dict[str, str]]:
    """
    Build one combined regex that matches any of the words.
    Returns (compiled_regex, normalized_key_to_color).
    """
    # Sort by length desc to prefer longer matches first
    words = sorted(color_table.keys(), key=len, reverse=True)

    # Escape for regex and optionally wrap with word boundaries
    escaped = []
    for w in words:
        ew = re.escape(w)
        if opts.whole_words:
            # \b has caveats for non-Latin scripts; offer a toggle in the dialog.
            ew = r"\b" + ew + r"\b"
        escaped.append(ew)

    pattern = "|".join(escaped) if escaped else r"(?!x)x"  # never matches if empty
    flags = re.IGNORECASE if opts.case_insensitive else 0
    return re.compile(pattern, flags), {k.lower() if opts.case_insensitive else k: v for k, v in color_table.items()}


def already_colored(text: str) -> bool:
    """
    Quick heuristic: detect if we've already wrapped via this add-on.
    We mark spans with class='cc-color' to avoid double-wrapping.
    """
    return 'class="cc-color"' in text or "class='cc-color'" in text


def apply_color_coding_to_html(
    html: str,
    regex: re.Pattern,
    key_to_color: Dict[str, str],
    opts: ColoringOptions,
) -> Tuple[str, int]:
    """
    Apply coloring to an HTML field, skipping content already wrapped by this add-on.
    Returns (new_html, replacements_count).
    """

    # Avoid double wrapping by ignoring content already wrapped with cc-color.
    # If you want to *refresh* colors, you could first normalize previous spans:
    # html = re.sub(r'<span class="cc-color"[^>]*>(.*?)</span>', r'\1', html)

    if not html or not regex.pattern:
        return html, 0

    # To reduce false matches inside tag attributes, we'll skip replacements
    # inside HTML tags by doing a light-weight scan: split by tags and only
    # apply replacements on text chunks.
    parts = re.split(r"(<[^>]+>)", html)
    changed = False
    total_replacements = 0

    def repl(m: re.Match) -> str:
        nonlocal total_replacements
        matched_text = m.group(0)
        key = matched_text.lower() if opts.case_insensitive else matched_text
        # Map back to canonical key (case-insensitive option)
        color = key_to_color.get(key)
        if color is None:
            # when case-insensitive and the matched text differs from keys,
            # find the original key by lower() lookup
            # For robustness, do another fallback: iterate once (rare).
            lk = matched_text.lower()
            color = key_to_color.get(lk)
        if color is None:
            return matched_text
        total_replacements += 1
        # Wrap with a recognizable class to avoid double wrapping later
        return f'<span class="cc-color" style="color:{color}">{matched_text}</span>'

    for i, chunk in enumerate(parts):
        # Process only text nodes (non-tag chunks)
        if i % 2 == 0 and chunk and "cc-color" not in chunk:
            new_chunk, n = regex.subn(repl, chunk)
            if n:
                changed = True
                total_replacements += 0  # already counted in repl
                parts[i] = new_chunk

    if not changed:
        return html, 0

    new_html = "".join(parts)
    return new_html, total_replacements


def note_is_cloze(note) -> bool:
    mt = note.note_type()
    # Anki models can be checked by type or name
    return (mt.get("type") == 1) or ("Cloze" in (mt.get("name") or ""))  # 1 is Cloze in older schema


def quote_deck_for_search(deck_name: str) -> str:
    # deck:"Name With Spaces"
    safe = deck_name.replace('"', '\\"')
    return f'deck:"{safe}"'


# =========================
# 4) The batch processor
# =========================

def color_notes_in_decks(
    deck_names: Iterable[str],
    include_children: bool,
    skip_cloze: bool,
    opts: ColoringOptions,
    dry_run: bool,
) -> Tuple[int, int, int]:
    """
    Returns (notes_seen, notes_modified, total_replacements).
    """
    color_table = get_color_table()
    regex, key_to_color = build_combined_regex(color_table, opts)
    if not color_table:
        raise RuntimeError("Color table is empty. Configure your color mappings first.")

    notes_seen = 0
    notes_modified = 0
    total_replacements = 0

    # Build search query
    queries = []
    for deck in deck_names:
        if include_children:
            # In Anki search, "deck:Parent::*" selects children
            # But the safest way is to just use deck:Parent and deck:Parent::*
            safe = deck.replace('"', '\\"')
            queries.append(f'(deck:"{safe}" OR deck:"{safe}::*")')
        else:
            queries.append(quote_deck_for_search(deck))

    if not queries:
        return 0, 0, 0

    search = " OR ".join(queries)

    mw.checkpoint("Color Coding Global")
    mw.progress.start(label="Color Coding: scanning notes…", immediate=True, min=0, max=0)
    try:
        nids = mw.col.find_notes(search)
        for idx, nid in enumerate(nids):
            if mw.progress.want_cancel():
                break

            note = mw.col.get_note(nid)
            notes_seen += 1

            if skip_cloze and note_is_cloze(note):
                continue

            # Apply to all fields
            modified = False
            replacements_for_note = 0
            for fname in note.keys():
                original = note[fname]
                # Skip if already colored to avoid repeated double work
                # (we still pass through the function since it won't double-wrap)
                new_val, num = apply_color_coding_to_html(original, regex, key_to_color, opts)
                if num > 0 and new_val != original:
                    if not dry_run:
                        note[fname] = new_val
                    modified = True
                    replacements_for_note += num

            if modified:
                notes_modified += 1
                total_replacements += replacements_for_note
                if not dry_run:
                    note.flush()

            # Occasionally yield to UI
            if idx % 200 == 0:
                mw.progress.update(label=f"Processing notes… ({idx+1}/{len(nids)})")

        if not dry_run:
            mw.reset()  # refresh Browser/Review if open

    finally:
        mw.progress.finish()

    return notes_seen, notes_modified, total_replacements


# =========================
# 5) Menu wiring
# =========================

def on_apply_to_selected_decks():
    if mw is None or mw.col is None:
        QMessageBox.warning(mw, "Color Coding", "Collection is not open.")
        return

    dlg = DeckPickerDialog(mw)
    
    result = _exec_dialog(dlg)
    if int(result) != _accepted_code():
        return


    decks = dlg.selected_decks()
    if not decks:
        tooltip("No decks selected.")
        return

    include_children = dlg.include_children()
    skip_cloze = dlg.skip_cloze()
    opts = ColoringOptions(
        whole_words=dlg.whole_words(),
        case_insensitive=dlg.case_insensitive(),
    )
    dry_run = dlg.dry_run()

    try:
        notes_seen, notes_modified, total_replacements = color_notes_in_decks(
            deck_names=decks,
            include_children=include_children,
            skip_cloze=skip_cloze,
            opts=opts,
            dry_run=dry_run,
        )
    except Exception as e:
        QMessageBox.critical(mw, "Color Coding – Error", f"{type(e).__name__}: {e}")
        return

    if dry_run:
        showInfo(
            f"Dry run complete.\n\n"
            f"Decks: {', '.join(decks)}\n"
            f"Include subdecks: {'Yes' if include_children else 'No'}\n"
            f"Notes scanned: {notes_seen}\n"
            f"Notes that would change: {notes_modified}\n"
            f"Total word matches: {total_replacements}\n"
            f"(No notes were modified.)"
        )
    else:
        showInfo(
            f"Color coding complete.\n\n"
            f"Decks: {', '.join(decks)}\n"
            f"Include subdecks: {'Yes' if include_children else 'No'}\n"
            f"Notes scanned: {notes_seen}\n"
            f"Notes modified: {notes_modified}\n"
            f"Total replacements made: {total_replacements}\n"
            f"You can undo via Edit → Undo (Color Coding Global)."
        )



def add_menu_action():
    menu = getattr(mw.form, "menuTools", None)
    if not menu:
        return
    # Create a proper submenu under Tools
    submenu = menu.addMenu("Color Coding (Global)")  # <-- simple title is correct
    action = QAction("Run Global Color Coding…", mw)
    action.triggered.connect(on_apply_to_selected_decks)
    # Optional: add a keyboard shortcut, e.g. Ctrl+Alt+C (Cmd+Alt+C on macOS)
    # action.setShortcut("Ctrl+Alt+C")
    submenu.addAction(action)

add_menu_action()


