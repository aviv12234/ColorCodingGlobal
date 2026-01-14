
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



from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QFileDialog, QColorDialog, QWidget, Qt, QMessageBox,
    QPlainTextEdit, QGuiApplication
)


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


import json
import os
from typing import Dict



# ---- Safe config helpers ----
def _read_cfg() -> dict:
    """Return this add-on's config dict; never None."""
    cfg = mw.addonManager.getConfig(__name__)
    return cfg if isinstance(cfg, dict) else {}

def _write_cfg(cfg: dict) -> None:
    """Persist config, ensuring it's a dict."""
    if not isinstance(cfg, dict):
        cfg = {}
    mw.addonManager.writeConfig(__name__, cfg)

def _ensure_cfg_initialized() -> dict:
    """
    Ensure config has the expected keys on first run.
    Returns the (possibly updated) config dict.
    """
    cfg = _read_cfg()
    
    if "color_entries" not in cfg or not isinstance(cfg["color_entries"], list):
        cfg["color_entries"] = []  # start empty list
        _write_cfg(cfg)
    return cfg


# --- CONFIG LOADER (used by batch run) ---

def get_color_table() -> Dict[str, str]:
    """
    Load {word: color} from config['color_entries'] (list of dicts with keys: word, color, group).
    Returns {} if nothing configured yet.
    """
    try:
        cfg = _ensure_cfg_initialized()
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
        return {}




# --- COLOR TABLE EDITOR DIALOG ---
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QFileDialog, QColorDialog, QWidget, Qt, QMessageBox
)
import json

class ColorTableEditor(QDialog):
    COL_WORD = 0
    COL_COLOR = 1
    COL_GROUP = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Color Table")
        self.resize(700, 420)

        main = QVBoxLayout(self)

        # Info
        main.addWidget(QLabel(
            "Define words and their colors. The format mirrors the original ColorCoding add-on.\n"
            "Columns: Word, Color (HTML name or HEX), Group (optional)."
        ))

        # Table
        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Word", "Color", "Group"])
        self.table.horizontalHeader().setStretchLastSection(True)
        main.addWidget(self.table)

        # Buttons row 1
        btns1 = QHBoxLayout()
        self.btn_add = QPushButton("Add row")
        self.btn_remove = QPushButton("Remove selected")
        self.btn_pick = QPushButton("Pick color…")
        btns1.addWidget(self.btn_add)
        btns1.addWidget(self.btn_remove)
        btns1.addWidget(self.btn_pick)
        btns1.addStretch(1)
        main.addLayout(btns1)


        # Buttons row 2 (import/export/clipboard)
        btns2 = QHBoxLayout()
        self.btn_import = QPushButton("Import JSON…")
        self.btn_export = QPushButton("Export JSON…")
        self.btn_paste = QPushButton("Paste JSON…")
        self.btn_copy  = QPushButton("Copy JSON")
        btns2.addWidget(self.btn_import)
        btns2.addWidget(self.btn_export)
        btns2.addSpacing(16)
        btns2.addWidget(self.btn_paste)
        btns2.addWidget(self.btn_copy)
        btns2.addStretch(1)
        main.addLayout(btns2)


        # OK/Cancel
        okrow = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_save = QPushButton("Save")
        okrow.addStretch(1)
        okrow.addWidget(self.btn_cancel)
        okrow.addWidget(self.btn_save)
        main.addLayout(okrow)

        # Wire
        self.btn_add.clicked.connect(self._add_row)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_pick.clicked.connect(self._pick_color_for_selected)
        self.btn_import.clicked.connect(self._import_json)
        self.btn_export.clicked.connect(self._export_json)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_paste.clicked.connect(self._paste_json_dialog)
        self.btn_copy.clicked.connect(self._copy_json_to_clipboard)


        # Load existing config into table
        self._load_from_config()

    # ---- helpers ----
    def _load_from_config(self):
        cfg = mw.addonManager.getConfig(__name__) or {}
        entries = cfg.get("color_entries", [])
        if not isinstance(entries, list):
            entries = []
        self.table.setRowCount(0)
        for row in entries:
            word = str((row.get("word") or "")).strip()
            color = str((row.get("color") or "")).strip()
            group = str((row.get("group") or "")).strip()
            self._append_row(word, color, group)

    def _append_row(self, word: str = "", color: str = "", group: str = ""):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, self.COL_WORD, QTableWidgetItem(word))
        self.table.setItem(r, self.COL_COLOR, QTableWidgetItem(color))
        self.table.setItem(r, self.COL_GROUP, QTableWidgetItem(group))

    def _add_row(self):
        self._append_row()

    def _remove_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def _current_row(self):
        idxs = self.table.selectedIndexes()
        return idxs[0].row() if idxs else -1

    def _pick_color_for_selected(self):
        r = self._current_row()
        if r < 0:
            QMessageBox.information(self, "Pick color", "Select a row first.")
            return
        # Suggest current color
        current = self.table.item(r, self.COL_COLOR)
        initial = (current.text() if current else "#FFFFFF") or "#FFFFFF"
        # QColorDialog returns QColor; handle gracefully
        qcolor = QColorDialog.getColor()
        if qcolor and qcolor.isValid():
            hexcolor = qcolor.name()  # '#RRGGBB'
            self.table.setItem(r, self.COL_COLOR, QTableWidgetItem(hexcolor))

    def _collect_entries(self):
        entries = []
        for r in range(self.table.rowCount()):
            w = self.table.item(r, self.COL_WORD)
            c = self.table.item(r, self.COL_COLOR)
            g = self.table.item(r, self.COL_GROUP)
            word = (w.text() if w else "").strip()
            color = (c.text() if c else "").strip()
            group = (g.text() if g else "").strip()
            if word and color:
                entries.append({"word": word, "group": group, "color": color})
        return entries

    def _on_save(self):
        entries = self._collect_entries()
        # Write into our add-on config
        cfg = mw.addonManager.getConfig(__name__) or {}
        cfg["color_entries"] = entries
        mw.addonManager.writeConfig(__name__, cfg)
        self.accept()

    def _import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import JSON", "", "JSON Files (*.json);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("JSON root must be a list of {word,group,color} objects")
            # Replace table content
            self.table.setRowCount(0)
            for row in data:
                if not isinstance(row, dict):
                    continue
                word = str(row.get("word", "")).strip()
                color = str(row.get("color", "")).strip()
                group = str(row.get("group", "")).strip()
                if word and color:
                    self._append_row(word, color, group)
        except Exception as e:
            QMessageBox.critical(self, "Import JSON", f"Failed to import: {e}")
    
    
    def _paste_json_dialog(self):
        """Open a small modal to paste JSON and load into the table."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Paste JSON")
        vbox = QVBoxLayout(dlg)
        vbox.addWidget(QLabel("Paste a JSON array of {word, group, color} objects:"))

        text = QPlainTextEdit(dlg)
        text.setPlaceholderText('[{"word":"penicillin","group":"","color":"red"}, ...]')
        text.setMinimumHeight(200)
        vbox.addWidget(text)

        btns = QHBoxLayout()
        btn_cancel = QPushButton("Cancel", dlg)
        btn_load = QPushButton("Load", dlg)
        btns.addStretch(1)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_load)
        vbox.addLayout(btns)

        def do_load():
            raw = text.toPlainText().strip()
            if not raw:
                QMessageBox.information(dlg, "Paste JSON", "Nothing to load.")
                return
            try:
                data = json.loads(raw)
                if not isinstance(data, list):
                    raise ValueError("JSON root must be a list")
                # Replace current table with parsed entries
                self.table.setRowCount(0)
                added = 0
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    word = str(row.get("word", "")).strip()
                    color = str(row.get("color", "")).strip()
                    group = str(row.get("group", "")).strip()
                    if word and color:
                        self._append_row(word, color, group)
                        added += 1
                if added == 0:
                    QMessageBox.warning(dlg, "Paste JSON", "No valid rows found (need 'word' and 'color').")
                    return
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "Paste JSON", f"Invalid JSON:\n{e}")

        btn_cancel.clicked.connect(dlg.reject)
        btn_load.clicked.connect(do_load)

        # Exec compat: Qt6/Qt5
        try:
            res = dlg.exec()
        except AttributeError:
            res = dlg.exec_()
        return res

    def _copy_json_to_clipboard(self):
        """Serialize current table to JSON and copy to clipboard."""
        entries = self._collect_entries()
        payload = json.dumps(entries, ensure_ascii=False, indent=2)
        cb = QGuiApplication.clipboard()
        cb.setText(payload)
        QMessageBox.information(self, "Copy JSON", "Current table copied to clipboard.")


    def _export_json(self):
        entries = self._collect_entries()
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON", "colorcoding_data.json", "JSON Files (*.json);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Export JSON", "Saved.")
        except Exception as e:
            QMessageBox.critical(self, "Export JSON", f"Failed to save: {e}")






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




def on_edit_color_table():
    dlg = ColorTableEditor(mw)
    res = _exec_dialog(dlg)
    if int(res) == _accepted_code():
        # Optional: small tooltip confirming save
        from aqt.utils import tooltip
        cfg = _read_cfg()
        entries = cfg.get("color_entries", [])
        tooltip(f"Saved {len(entries)} color entries", parent=mw)

def add_menu_action():
    menu = getattr(mw.form, "menuTools", None)
    if not menu:
        return
    submenu = menu.addMenu("Color Coding Global")
    action_run = QAction("Apply to Selected Decks…", mw)
    action_run.triggered.connect(on_apply_to_selected_decks)
    submenu.addAction(action_run)

    # NEW: editor
    action_edit = QAction("Edit Color Table…", mw)
    action_edit.triggered.connect(on_edit_color_table)
    submenu.addAction(action_edit)


if "mw" in globals() and mw:
    _ensure_cfg_initialized()


add_menu_action()


