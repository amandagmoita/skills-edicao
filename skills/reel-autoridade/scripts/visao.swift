// visao.swift — rosto e recorte de pessoa com o Apple Vision (nada pra instalar).
//
// Compilar uma vez (o rodar.sh faz isso sozinho):
//   swiftc -O visao.swift -o bin/visao
//
// Uso:
//   visao rosto <pasta_de_frames> <saida.json>
//       Lê os .jpg/.png da pasta, detecta o maior rosto em cada um e grava a MEDIANA
//       da caixa em coordenadas normalizadas com origem no canto SUPERIOR esquerdo:
//       {"x":..,"y":..,"w":..,"h":..,"cx":..,"cy":..,"amostras":N}
//
//   visao mascara <pasta_de_frames> <pasta_saida>
//       Para cada frame gera uma máscara PNG em tons de cinza (branco = pessoa),
//       mesmo nome de arquivo, na resolução do frame de entrada.
import Foundation
import Vision
import CoreImage
import ImageIO
import UniformTypeIdentifiers

func frames(_ dir: String) -> [URL] {
    let fm = FileManager.default
    let itens = (try? fm.contentsOfDirectory(atPath: dir)) ?? []
    return itens.filter { $0.hasSuffix(".jpg") || $0.hasSuffix(".png") }
        .sorted()
        .map { URL(fileURLWithPath: dir).appendingPathComponent($0) }
}

func mediana(_ v: [Double]) -> Double {
    let s = v.sorted()
    return s.isEmpty ? 0 : s[s.count / 2]
}

func rosto(_ dir: String, _ saida: String) throws {
    var xs: [Double] = [], ys: [Double] = [], ws: [Double] = [], hs: [Double] = []
    for url in frames(dir) {
        let req = VNDetectFaceRectanglesRequest()
        try VNImageRequestHandler(url: url).perform([req])
        guard let maior = (req.results ?? []).max(by: {
            $0.boundingBox.width * $0.boundingBox.height < $1.boundingBox.width * $1.boundingBox.height
        }) else { continue }
        let b = maior.boundingBox  // origem embaixo à esquerda
        xs.append(Double(b.minX)); ys.append(Double(1 - b.maxY))
        ws.append(Double(b.width)); hs.append(Double(b.height))
    }
    guard !xs.isEmpty else {
        FileHandle.standardError.write("nenhum rosto encontrado\n".data(using: .utf8)!)
        exit(2)
    }
    let x = mediana(xs), y = mediana(ys), w = mediana(ws), h = mediana(hs)
    let json: [String: Any] = ["x": x, "y": y, "w": w, "h": h,
                               "cx": x + w / 2, "cy": y + h / 2, "amostras": xs.count]
    let data = try JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: URL(fileURLWithPath: saida))
    print("rosto: \(xs.count) amostras -> \(saida)")
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
guard args.count == 4 else {
    print("uso: visao rosto <frames> <saida.json> | visao mascara <frames> <pasta_saida>")
    exit(1)
}
do {
    switch args[1] {
    case "rosto": try rosto(args[2], args[3])
    case "mascara": try mascara(args[2], args[3])
    default: print("modo desconhecido: \(args[1])"); exit(1)
    }
} catch {
    FileHandle.standardError.write("erro: \(error)\n".data(using: .utf8)!)
    exit(1)
}
