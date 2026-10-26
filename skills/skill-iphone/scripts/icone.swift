// icone.swift — salva o ícone de um app do Mac como PNG (o mesmo que o Finder mostra).
// Uso: icone <caminho do .app> <saida.png> [lado]
import AppKit

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("uso: icone <app> <saida.png> [lado]\n".data(using: .utf8)!)
    exit(1)
}
let lado = args.count > 3 ? CGFloat(Double(args[3]) ?? 1024) : 1024
let icone = NSWorkspace.shared.icon(forFile: args[1])
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(lado), pixelsHigh: Int(lado),
                           bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
icone.draw(in: NSRect(x: 0, y: 0, width: lado, height: lado), from: .zero, operation: .copy, fraction: 1)
NSGraphicsContext.restoreGraphicsState()
guard let png = rep.representation(using: .png, properties: [:]) else { exit(2) }
try! png.write(to: URL(fileURLWithPath: args[2]))
