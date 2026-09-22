<template>
  <canvas ref="canvasEl" class="board" :style="{ opacity: loading ? 0.4 : 1 }" />
</template>

<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from "vue";
import { fetchAuthBlob } from "../api/labels";

export type OverlayPanel = {
  title: string;
  colorUrl?: string | null;
};

const props = defineProps<{
  originUrl: string;
  panels: OverlayPanel[];
  alpha: number;
}>();

const HEADER_H = 36;
const GAP = 8;
const PANEL_BG = "#202428";
const TEXT = "#e8e4d9";

const canvasEl = ref<HTMLCanvasElement | null>(null);
const loading = ref(false);
let originData: ImageData | null = null;
let colorByUrl = new Map<string, ImageData>();
let panelWidth = 0;
let panelHeight = 0;
let loadToken = 0;

watch(
  () => [props.originUrl, props.panels.map((row) => `${row.title}:${row.colorUrl ?? ""}`).join("|")] as const,
  () => {
    void reload();
  },
  { immediate: true },
);

watch(
  () => props.alpha,
  () => {
    paint();
  },
);

onUnmounted(() => {
  loadToken += 1;
  originData = null;
  colorByUrl = new Map();
});

async function reload() {
  const token = ++loadToken;
  originData = null;
  colorByUrl = new Map();
  if (!props.originUrl) return;
  loading.value = true;
  try {
    const originBmp = await blobToBitmap(await fetchAuthBlob(props.originUrl));
    panelWidth = originBmp.width;
    panelHeight = originBmp.height;
    originData = bitmapToImageData(originBmp, panelWidth, panelHeight);
    originBmp.close();
    for (const panel of props.panels) {
      if (!panel.colorUrl) continue;
      const bmp = await blobToBitmap(await fetchAuthBlob(panel.colorUrl));
      colorByUrl.set(panel.colorUrl, bitmapToImageData(bmp, panelWidth, panelHeight));
      bmp.close();
    }
    if (token !== loadToken) return;
    await nextTick();
    paint();
  } catch {
    if (token === loadToken) {
      originData = null;
    }
  } finally {
    if (token === loadToken) loading.value = false;
  }
}

async function blobToBitmap(blob: Blob): Promise<ImageBitmap> {
  return createImageBitmap(blob);
}

function bitmapToImageData(bitmap: ImageBitmap, width: number, height: number): ImageData {
  const scratch = document.createElement("canvas");
  scratch.width = width;
  scratch.height = height;
  const ctx = scratch.getContext("2d");
  if (!ctx) return new ImageData(width, height);
  ctx.drawImage(bitmap, 0, 0, width, height);
  return ctx.getImageData(0, 0, width, height);
}

function paint() {
  const canvas = canvasEl.value;
  const origin = originData;
  if (!canvas || !origin || !props.panels.length) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const count = props.panels.length;
  const width = count * panelWidth + Math.max(0, count - 1) * GAP;
  const height = HEADER_H + panelHeight;
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  ctx.fillStyle = PANEL_BG;
  ctx.fillRect(0, 0, width, height);
  ctx.font = "13px sans-serif";
  ctx.fillStyle = TEXT;
  ctx.textBaseline = "middle";
  const strength = Math.min(1, Math.max(0, props.alpha / 100));
  props.panels.forEach((panel, index) => {
    const x = index * (panelWidth + GAP);
    ctx.fillStyle = PANEL_BG;
    ctx.fillRect(x, 0, panelWidth, HEADER_H);
    ctx.fillStyle = TEXT;
    ctx.fillText(panel.title, x + 10, HEADER_H / 2);
    const color = panel.colorUrl ? colorByUrl.get(panel.colorUrl) : undefined;
    const panelData = color ? blendDefects(origin, color, strength) : origin;
    ctx.putImageData(panelData, x, HEADER_H);
  });
}

function blendDefects(origin: ImageData, color: ImageData, alpha: number): ImageData {
  const out = new ImageData(origin.width, origin.height);
  const src = origin.data;
  const tint = color.data;
  const dst = out.data;
  for (let i = 0; i < src.length; i += 4) {
    const defect = tint[i] > 8 || tint[i + 1] > 8 || tint[i + 2] > 8;
    if (!defect || alpha <= 0) {
      dst[i] = src[i];
      dst[i + 1] = src[i + 1];
      dst[i + 2] = src[i + 2];
    } else {
      dst[i] = src[i] * (1 - alpha) + tint[i] * alpha;
      dst[i + 1] = src[i + 1] * (1 - alpha) + tint[i + 1] * alpha;
      dst[i + 2] = src[i + 2] * (1 - alpha) + tint[i + 2] * alpha;
    }
    dst[i + 3] = 255;
  }
  return out;
}
</script>

<style scoped>
.board {
  max-width: 100%;
  height: auto;
  display: block;
}
</style>
