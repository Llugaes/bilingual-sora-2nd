"""Audit all book pages against raw eight-locale resources and the real JS renderer."""

import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables, build_table_entries
from sora_bilingual.localization.menu_tables import sections
from tools.inspect_status_sprite_layout import Layout


RUNNER = r"""
const fs=require('fs'),assert=require('node:assert/strict');
const {RuntimeBooks}=require('./sora_bilingual/game/scripts/runtime_books');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');
const raw=JSON.parse(fs.readFileSync(0,'utf8')),locales=Object.keys(raw);
let documents=0,pagesChecked=0,renders=0,maxPages=0;const start=performance.now();
for(const source of locales)for(const primary of locales)for(const secondary of locales) {
 for(const id of Object.keys(raw[source])) {
  const doc={source:raw[source][id],primary:raw[primary][id],secondary:raw[secondary][id]};
  const books=new RuntimeBooks({[id]:doc},RuntimeText);
  for(const style of [{},{rubyScale:1,rubyGap:8,lineGap:24,offsetY:24}]) {
   const pages=books.pages(id,'annotation',style);assert.ok(pages,JSON.stringify({source,primary,secondary,id}));
   maxPages=Math.max(maxPages,pages.length);
   for(const side of ['primary','secondary']) {
    // No whitespace folding: every source line and paragraph separator must
    // survive in order, exactly once, including the old unpaired last pages.
    assert.equal(pages.flatMap(p=>p[side+'Lines']?p[side].split('\n'):[]).join('\n'),doc[side].map(p=>p[1]).join('\n'));
    if(side==='primary')assert.deepEqual(RuntimeBooks.runs(pages.map(p=>[p.image,p.primary])).map(r=>r.image),RuntimeBooks.runs(doc.primary).map(r=>r.image));
   }
   for(let i=0;i<pages.length;i++) {
    const page=pages[i];assert.equal(doc.source[page.nativePage-1][1],page.source);
    assert.ok(page.primary.split('\n').length<=RuntimeBooks.lineBudget(style));
    assert.ok(page.secondary.split('\n').length<=RuntimeBooks.lineBudget(style));
    for(const side of ['primary','secondary'])assert.equal((page[side].match(/<R>/g)||[]).length,(page[side].match(/<\/R[^>]*>/g)||[]).length,'native reading split at page boundary');
    if(source==='zh-Hans'&&[['zh-Hans','ja'],['zh-Hans','en'],['en','ja']].some(p=>p[0]===primary&&p[1]===secondary)) {
     const tr=new RuntimeText(books.context(id,i+1,page.source,'annotation',style).model);
     assert.equal(tr.translate(page.source,'primary'),page.primary.trim()?page.primary:page.secondary);assert.equal(tr.translate(page.source,'secondary'),page.primary.trim()?page.secondary:page.primary);
     const plan=tr.render(page.source,'annotation');
     if(page.primary.trim()&&page.secondary.trim()&&RuntimeText.needsAnnotation(page.primary,page.secondary))assert.notEqual(plan.kind,'plain');
     renders++;
    }
    pagesChecked++;
   }
  }
  for(const mode of ['primary','secondary'])assert.deepEqual(books.pages(id,mode).map(p=>[p.image,p[mode]]),doc[mode]);
  documents++;
 }
}
process.stdout.write(JSON.stringify({language_configurations:locales.length**3,documents,pages_checked:pagesChecked,final_render_cases:renders,max_pages:maxPages,seconds:(performance.now()-start)/1000,all_passed:true}));
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/todo-book-documents.json")
    args = parser.parse_args()
    raw, counts = {}, {}
    for language, name in _TABLE_ARCHIVES.items():
        with FpacArchive(args.game_dir / "pac/steam" / name) as archive:
            data = archive.read(_logical_tables(archive)["table/t_books.tbl"])
        _, start, size, count = next(s for s in sections(data) if s[0] == "BooksText")
        assert size == 24
        books = {}
        for row in range(count):
            at = start + row * size
            book, page = struct.unpack_from("<HH", data, at)
            body, image = struct.unpack_from("<QQ", data, at + 8)
            pages = books.setdefault(str(book), [])
            assert page == len(pages) + 1
            pages.append(
                [
                    data[image : data.index(0, image)].decode(),
                    data[body : data.index(0, body)].decode(),
                ]
            )
        raw[language] = books
        counts[language] = {"chapters": len(books), "physical_pages": count}
    with FpacArchive(args.game_dir / "pac/steam/layout.pac") as archive:
        data = archive.read("layout/note_books.lay")
    layout = Layout(data, "layout/note_books.lay", (127, 0))
    body = next(node for node in layout.all_nodes() if layout.node_name(node) == "contents_text")
    scalars = {
        layout.key(c): layout.number(c) for c in layout.refs(body) if layout.number(c) is not None
    }
    assert {key: scalars[key] for key in (51, 136, 842, 812)} == {
        51: 680,
        136: 670,
        842: 30,
        812: 9,
    }
    entries, audit = build_table_entries(args.game_dir)
    books = [e for e in entries if "book_pages" in e]
    assert len(books) == len(raw["ja"])
    for entry in books:
        for locale in raw:
            assert entry["book_pages"][locale] == raw[locale][str(entry["book_id"])]
    result = subprocess.run(
        ["node", "-e", RUNNER],
        input=json.dumps(raw),
        text=True,
        encoding="utf-8",
        capture_output=True,
        cwd=ROOT,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    report = {
        "game_attached": False,
        "raw": counts,
        "catalogue_documents": len(books),
        **json.loads(result.stdout),
    }
    args.output.write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
