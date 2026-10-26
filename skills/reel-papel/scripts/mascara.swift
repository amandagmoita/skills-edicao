// mascara.swift — recorte da pessoa com o Apple Vision (nada pra instalar).
//
// Compilar (o mascaras.py faz sozinho na 1ª vez):
//   swiftc -O mascara.swift -o bin/mascara
//
// Uso:
//   mascara <pasta_de_frames> <pasta_saida>
//       Para cada .png/.jpg gera uma máscara PNG em tons de cinza (branco = pessoa),
//       mesmo nome de arquivo, na resolução do frame de entrada.
import Foundation
import Vision
import CoreImage
import ImageIO
import UniformTypeIdentifiers

func frames(_ dir: String) -> [URL] {
    let itens = (try? FileManager.default.contentsOfDirectory(atPath: dir)) ?? []
    return itens.filter { $0.hasSuffix(".jpg") || $0.hasSuffix(".png") }
        .sorted()
        .map { URL(fileURLWithPath: dir).appendingPathComponent($0) }
}

func mascara(_ dir: String, _ saida: String) throws {
    try FileManager.default.createDirectory(atPath: saida, withIntermediateDirectories: true)
    let ctx = CIContext()
    let lista = frames(dir)
    for (i, url) in lista.enumerated() {
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
              let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { continue }
        let req = VNGeneratePersonSegmentationRequest()
        req.qualityLevel = .accurate
        req.outputPixelFormat = kCVPixelFormatType_OneComponent8
        try VNImageRequestHandler(cgImage: img).perform([req])
        guard let buf = req.results?.first?.pixelBuffer else { continue }
        var m = CIImage(cvPixelBuffer: buf)
        let sx = CGFloat(img.width) / m.extent.width, sy = CGFloat(img.height) / m.extent.height
        m = m.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
        let destino = URL(fileURLWithPath: saida).appendingPathComponent(
            url.deletingPathExtension().lastPathComponent + ".png")
        guard let cg = ctx.createCGImage(m, from: CGRect(x: 0, y: 0, width: img.width, height: img.height),
                                         format: .L8, colorSpace: CGColorSpaceCreateDeviceGray()),
              let dst = CGImageDestinationCreateWithURL(destino as CFURL, UTType.png.identifier as CFString, 1, nil)
        else { continue }
        CGImageDestinationAddImage(dst, cg, nil)
        CGImageDestinationFinalize(dst)
        if i % 30 == 0 { print("mascara \(i + 1)/\(lista.count)") }
    }
    print("mascaras -> \(saida)")
}

let args = CommandLine.arguments
guard args.count == 3 else {
    print("uso: mascara <pasta_de_frames> <pasta_saida>")
    exit(1)
}
do {
    try mascara(args[1], args[2])
} catch {
    FileHandle.standardError.write("erro: \(error)\n".data(using: .utf8)!)
    exit(1)
}
