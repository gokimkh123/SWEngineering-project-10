// 올리기 전에 브라우저에서 사진을 줄인다 (공개 서버 앞단 Cloudflare 무료 한도·느린 회선 대비).
// 서버가 쓰는 것은 썸네일·VLM용 축소본(512px)·촬영 시각과 위치(EXIF)뿐이라 긴 변 2048px면 충분하다.
// JPEG는 원본의 EXIF 조각(APP1)을 그대로 옮겨 붙여 촬영 시각·GPS를 지킨다. 방향은 이미 돌려 그렸으므로 방향 값만 1로 바꾼다.
// HEIC·PNG, 작은 사진, 줄여도 작아지지 않는 사진, 처리 중 오류가 나면 원본을 그대로 보낸다.

const MAX_SIDE = 2048
const QUALITY = 0.88
const SKIP_BELOW = 1.5 * 1024 * 1024

function isJpeg(file) {
  return file.type === 'image/jpeg' || /\.jpe?g$/i.test(file.name)
}

/** JPEG 안의 EXIF APP1 조각(마커 포함)을 찾아 복사본을 돌려준다. 없으면 null. */
export function findExifSegment(bytes) {
  if (bytes[0] !== 0xff || bytes[1] !== 0xd8) return null
  let i = 2
  while (i + 4 <= bytes.length) {
    if (bytes[i] !== 0xff) return null
    const marker = bytes[i + 1]
    if (marker === 0xda || marker === 0xd9) return null // 영상 데이터 시작 → EXIF 없음
    const len = (bytes[i + 2] << 8) | bytes[i + 3]
    if (marker === 0xe1 && bytes[i + 4] === 0x45 && bytes[i + 5] === 0x78 && bytes[i + 6] === 0x69 && bytes[i + 7] === 0x66) {
      return bytes.slice(i, i + 2 + len)
    }
    i += 2 + len
  }
  return null
}

/** EXIF 조각의 IFD0 방향(0x0112) 값을 1(그대로)로 바꾼다. */
export function resetOrientation(seg) {
  const tiff = 10 // FF E1 + 길이(2) + "Exif\0\0"(6)
  const view = new DataView(seg.buffer, seg.byteOffset, seg.byteLength)
  if (seg.length < tiff + 8) return seg
  const le = view.getUint16(tiff) === 0x4949
  const ifd0 = tiff + view.getUint32(tiff + 4, le)
  if (ifd0 + 2 > seg.length) return seg
  const n = view.getUint16(ifd0, le)
  for (let k = 0; k < n; k++) {
    const e = ifd0 + 2 + k * 12
    if (e + 12 > seg.length) break
    if (view.getUint16(e, le) === 0x0112) view.setUint16(e + 8, 1, le)
  }
  return seg
}

/** 새 JPEG의 SOI(FF D8) 바로 뒤에 EXIF 조각을 넣는다. */
export function insertExif(jpeg, seg) {
  const out = new Uint8Array(jpeg.length + seg.length)
  out.set(jpeg.subarray(0, 2), 0)
  out.set(seg, 2)
  out.set(jpeg.subarray(2), 2 + seg.length)
  return out
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => resolve({ img, url })
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('decode')) }
    img.src = url // <img>는 EXIF 방향대로 돌려서 그린다
  })
}

export async function shrinkPhoto(file) {
  if (!isJpeg(file) || file.size < SKIP_BELOW) return file
  try {
    const bytes = new Uint8Array(await file.arrayBuffer())
    const exif = findExifSegment(bytes)
    const { img, url } = await loadImage(file)
    const w = img.naturalWidth
    const h = img.naturalHeight
    const scale = Math.min(1, MAX_SIDE / Math.max(w, h))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(w * scale)
    canvas.height = Math.round(h * scale)
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
    URL.revokeObjectURL(url)
    const blob = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', QUALITY))
    if (!blob) return file
    let out = new Uint8Array(await blob.arrayBuffer())
    if (exif) out = insertExif(out, resetOrientation(exif))
    if (out.length >= file.size) return file
    return new File([out], file.name, { type: 'image/jpeg', lastModified: file.lastModified })
  } catch {
    return file
  }
}
