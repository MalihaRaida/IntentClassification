/**
 * Backend for the review-intent annotation page.
 *
 * Paste this into Extensions > Apps Script of the Google Sheet that will hold
 * the labels, run setup() once, then deploy as a web app
 * (Execute as: Me, Who has access: Anyone). See SETUP.md.
 *
 * Sheets:
 *   Annotators  code | name        one row per annotator; the code is their login
 *   Labels      one row per (annotator, item), upserted on every save
 */

const ANNOTATORS_SHEET = "Annotators";
const LABELS_SHEET = "Labels";
const LABEL_HEADERS = [
  "key", "annotator_code", "annotator_name", "item_id", "labels",
  "confidence", "rationale", "flag", "status", "updated_at", "saved_at",
];
const CONFIDENCE = ["High", "Medium", "Low", ""];
const LABEL_CODES = ["RC", "SP", "RQ", "CN", "EX", "AK", "CR", "VF", "OB", "AT"];

function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let ann = ss.getSheetByName(ANNOTATORS_SHEET);
  if (!ann) {
    ann = ss.insertSheet(ANNOTATORS_SHEET);
    ann.getRange(1, 1, 3, 2).setValues([["code", "name"], ["ANN-A7Q2", "Annotator 1"], ["ANN-K9P4", "Annotator 2"]]);
    ann.setFrozenRows(1);
  }
  let labels = ss.getSheetByName(LABELS_SHEET);
  if (!labels) {
    labels = ss.insertSheet(LABELS_SHEET);
    labels.getRange(1, 1, 1, LABEL_HEADERS.length).setValues([LABEL_HEADERS]);
    labels.setFrozenRows(1);
  }
  // Plain text everywhere, so a rationale starting with "=" is never run as a formula.
  labels.getRange(1, 1, labels.getMaxRows(), LABEL_HEADERS.length).setNumberFormat("@");
}

function doGet(e) {
  const p = e.parameter || {};
  if (p.action === "load") return json_(load_(p.code));
  return json_({ ok: true, service: "review-intent-annotation" });
}

function doPost(e) {
  let body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return json_({ ok: false, error: "bad_request" });
  }
  if (body.action === "save") return json_(save_(body.code, body.items));
  return json_({ ok: false, error: "unknown_action" });
}

function annotator_(code) {
  code = String(code || "").trim().toUpperCase();
  if (!code) return null;
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ANNOTATORS_SHEET);
  const rows = sheet.getDataRange().getValues().slice(1);
  for (const r of rows) {
    if (String(r[0]).trim().toUpperCase() === code) return { code: String(r[0]).trim(), name: String(r[1] || "").trim() };
  }
  return null;
}

function load_(code) {
  const a = annotator_(code);
  if (!a) return { ok: false, error: "bad_code" };
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(LABELS_SHEET);
  const values = sheet.getDataRange().getValues().slice(1);
  const items = values
    .filter((r) => r[1] === a.code)
    .map((r) => ({
      item_id: Number(r[3]),
      labels: String(r[4] || "").split(";").filter(Boolean),
      confidence: String(r[5] || ""),
      rationale: String(r[6] || ""),
      flag: String(r[7]) === "TRUE" || r[7] === true,
      updated_at: String(r[9] || ""),
    }));
  return { ok: true, code: a.code, name: a.name, items };
}

function save_(code, items) {
  const a = annotator_(code);
  if (!a) return { ok: false, error: "bad_code" };
  if (!Array.isArray(items) || !items.length || items.length > 400) return { ok: false, error: "bad_request" };

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(LABELS_SHEET);
    const last = sheet.getLastRow();
    const keys = last > 1 ? sheet.getRange(2, 1, last - 1, 1).getValues().map((r) => r[0]) : [];
    const rowOf = new Map(keys.map((k, i) => [k, i + 2]));
    const now = new Date().toISOString();
    const appends = [];

    const latest = new Map();
    for (const it of items) latest.set(Math.floor(Number(it.item_id)), it);

    for (const [id, it] of latest) {
      if (!(id > 0)) continue;
      const key = a.code + "|" + id;
      const row = [
        key, a.code, a.name, String(id),
        (it.labels || []).filter((l) => LABEL_CODES.indexOf(l) >= 0).slice(0, 1).join(";"),  // one label per item
        CONFIDENCE.indexOf(it.confidence) >= 0 ? it.confidence : "",
        String(it.rationale || "").slice(0, 5000),
        it.flag ? "TRUE" : "FALSE",
        String(it.status || "").slice(0, 20),
        String(it.updated_at || "").slice(0, 40),
        now,
      ];
      const existing = rowOf.get(key);
      if (existing) sheet.getRange(existing, 1, 1, row.length).setNumberFormat("@").setValues([row]);
      else appends.push(row);
    }
    if (appends.length) {
      sheet.getRange(sheet.getLastRow() + 1, 1, appends.length, LABEL_HEADERS.length).setNumberFormat("@").setValues(appends);
    }
  } finally {
    lock.releaseLock();
  }
  return { ok: true, saved: items.length };
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
