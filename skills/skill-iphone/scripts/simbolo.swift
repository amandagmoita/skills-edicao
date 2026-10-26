// simbolo.swift — salva um SF Symbol (os ícones do próprio macOS/iOS) como PNG preto em fundo transparente.
// Uso: simbolo <nome do símbolo> <saida.png> [lado]
// Ex.: simbolo gearshape.fill engrenagem.png 512   (nomes: app "SF Symbols" ou developer.apple.com/sf-symbols)
import AppKit

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("uso: simbolo <nome> <saida.png> [lado]\n".data(using: .utf8)!)
    exit(1)
}
let lado = args.count > 3 ? CGFloat(Double(args[3]) ?? 512) : 512
let cfg = NSImage.SymbolConfiguration(pointSize: lado * 0.8, weight: .semibold)
guard let base = NSImage(systemSymbolName: args[1], accessibilityDescription: nil),
      let sym = base.withSymbolConfiguration(cfg) else {
    FileHandle.standardError.write("símbolo não existe: \(args[1])\n".data(using: .utf8)!)
    exit(2)
}
let sz = sym.size
let esc = min(lado / sz.width, lado / sz.height)
let w = Int(sz.width * esc), h = Int(sz.height * esc)
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h,
                           bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
sym.draw(in: NSRect(x: 0, y: 0, width: w, height: h), from: .zero, operation: .sourceOver, fraction: 1)
NSGraphicsContext.restoreGraphicsState()
guard let png = rep.representation(using: .png, properties: [:]) else { exit(3) }
try! png.write(to: URL(fileURLWithPath: args[2]))
