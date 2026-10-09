// Store-only ZIP: reproducible, no dependency or platform-specific archive command.
import { readdirSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const folder = resolve(root, 'watch-extension')
function crc32(bytes) {
  let crc = 0xffffffff
  for (const byte of bytes) {
    crc ^= byte
    for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0)
  }
  return (crc ^ 0xffffffff) >>> 0
}
const chunks = [], directory = []
let offset = 0
for (const file of readdirSync(folder).sort()) {
  const name = Buffer.from(file)
  const data = readFileSync(resolve(folder, file))
  const crc = crc32(data)
  const header = Buffer.alloc(30)
  header.writeUInt32LE(0x04034b50, 0)
  header.writeUInt16LE(20, 4)
  header.writeUInt16LE(0x21, 12) // 1980-01-01, valid DOS date for Windows extraction.
  header.writeUInt32LE(crc, 14)
  header.writeUInt32LE(data.length, 18)
  header.writeUInt32LE(data.length, 22)
  header.writeUInt16LE(name.length, 26)
  const central = Buffer.alloc(46)
  central.writeUInt32LE(0x02014b50, 0)
  central.writeUInt16LE(20, 4)
  central.writeUInt16LE(20, 6)
  central.writeUInt16LE(0x21, 14)
  central.writeUInt32LE(crc, 16)
  central.writeUInt32LE(data.length, 20)
  central.writeUInt32LE(data.length, 24)
  central.writeUInt16LE(name.length, 28)
  central.writeUInt32LE(offset, 42)
  chunks.push(header, name, data)
  directory.push(central, name)
  offset += header.length + name.length + data.length
}
const central = Buffer.concat(directory)
const end = Buffer.alloc(22)
end.writeUInt32LE(0x06054b50, 0)
end.writeUInt16LE(directory.length / 2, 8)
end.writeUInt16LE(directory.length / 2, 10)
end.writeUInt32LE(central.length, 12)
end.writeUInt32LE(offset, 16)
mkdirSync(resolve(root, 'public'), { recursive: true })
writeFileSync(resolve(root, 'public/watch-extension.zip'), Buffer.concat([...chunks, central, end]))
