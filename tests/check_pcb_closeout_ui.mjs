// Read-only source checks for C3 mask contracts and C5 DEFERRED / NOT_SUPPORTED.
// This does not implement or simulate a cancellation API.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.resolve(process.argv[2] || path.join(root, 'docs/report/pcb-stage4-closeout-20261030/frontend'));
const files = [
  'apps/web/src/views/pcb/PcbNewView.vue',
  'apps/web/src/views/pcb/PcbTaskView.vue',
  'apps/web/src/views/pcb/types.ts',
  'apps/web/src/views/records/RecordsView.vue',
  'apps/web/src/components/TaskStatus.vue',
  'apps/web/src/api/http.ts',
  'apps/web/src/api/labels.ts',
  'apps/api/app/routers/pcb_segmentation.py',
  'apps/api/app/routers/tasks.py',
  'apps/api/app/db/models.py',
];
const sources = Object.fromEntries(await Promise.all(files.map(async file => [file, await fs.readFile(path.join(root, file), 'utf8')])));
const assertions = [];
const check = (condition, message) => { assert.ok(condition, message); assertions.push(message); console.log(`PASS ${message}`); };
for (const [file, source] of Object.entries(sources)) {
  check(!/\b(?:canceled|canceling|cancelled|cancelling)\b/i.test(source), `${file}: no fabricated cancellation state`);
  check(!/(?:http\.(?:post|put|patch|delete)|@router\.(?:post|put|patch|delete))\([^\n]*(?:\/cancel|\/abort|\/terminate)/i.test(source), `${file}: no unsupported cancellation endpoint or client call`);
  if (file.endsWith('.vue')) {
    const controls = source.match(/<(?:el-button|button|router-link|el-dropdown-item)\b[^>]*>[\s\S]*?<\/(?:el-button|button|router-link|el-dropdown-item)>/g) || [];
    check(controls.every(text => !/取消任务|中止任务|终止任务|停止任务|cancel task/i.test(text)), `${file}: no false cancellation control`);
  }
}
check(sources[files[2]].includes('任务取消本期延期，当前不支持主动中止已提交任务'), 'exact required cancellation deferral notice exists');
for (const file of files.slice(0, 2)) check(sources[file].includes('class="pcb-muted pcb-cancel-notice">{{ PCB_CANCEL_NOTICE }}'), `${file}: deferral notice is rendered for all task/service states`);
const detail = sources[files[1]];
check(detail.includes('原始二值掩码（0/1）') && detail.includes('可视化掩码（0/255）'), 'raw and visual mask labels expose exact numeric contracts');
check(detail.includes("!artifact('mask_visual') && artifact('pred_mask')") && detail.includes('下载仍保留原始 0/1'), 'legacy task fallback truthfully retains raw values');
check(detail.includes("['pred_mask','gt'].includes(selected)") && !detail.includes("['pred_mask','mask_visual'"), 'visual PNG is not routed through raw-mask brightness CSS');
check(sources[files[2]].includes('"mask_visual"'), 'frontend artifact type includes distinct visual mask kind');
await fs.mkdir(output, { recursive: true });
await fs.writeFile(path.join(output, 'static-results.json'), JSON.stringify({checks:assertions.length, assertions, files, cancellation:'DEFERRED / NOT_SUPPORTED', environment:'Read-only source audit; no backend requests; no production configuration'}, null, 2));
console.log(`PASS ${assertions.length} PCB closeout static assertions.`);
