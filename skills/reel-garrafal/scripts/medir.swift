// medir.swift — onde está a pessoa no quadro (Apple Vision, nada pra instalar).
//
// Compilar (o medir.py faz sozinho na 1ª vez):
//   swiftc -O medir.swift -o bin/medir
//
// Uso:
//   medir <pasta_de_frames>
//       Para cada .png/.jpg imprime uma linha JSON:
//       {"arquivo": "...", "topo": y, "rosto": [x, y, w, h] | null}
//       topo  = 1ª linha (de cima pra baixo) com pessoa na faixa central (cabelo incluso)
//       rosto = caixa do rosto (testa ao queixo), em pixels, origem no canto de cima
import Foundation
import Vision
import ImageIO

func frames(_ dir: String) -> [URL] {
    let itens = (try? FileManager.default.contentsOfDirectory(atPath: dir)) ?? []
    return itens.filter { $0.hasSuffix(".jpg") || $0.hasSuffix(".png") }
        .sorted()
        .map { URL(fileURLWithPath: dir).appendingPathComponent($0) }
}

func topoPessoa(_ img: CGImage) throws -> Int? {
    let req = VNGeneratePersonSegmentationRequest()
    req.qualityLevel = .accurate
    req.outputPixelFormat = kCVPixelFormatType_OneComponent8
    try VNImageRequestHandler(cgImage: img).perform([req])
    guard let buf = req.results?.first?.pixelBuffer else { return nil }
    CVPixelBufferLockBaseAddress(buf, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(buf, .readOnly) }
    let w = CVPixelBufferGetWidth(buf), h = CVPixelBufferGetHeight(buf)
    let bpr = CVPixelBufferGetBytesPerRow(buf)
    guard let base = CVPixelBufferGetBaseAddress(buf) else { return nil }
    let p = base.assumingMemoryBound(to: UInt8.self)
    let x0 = Int(Double(w) * 0.2), x1 = Int(Double(w) * 0.8)
    let minimo = max(3, (x1 - x0) / 40)   // ~2,5% da faixa: ignora fio de cabelo solto
    for y in 0..<h {
        var n = 0
        for x in x0..<x1 where p[y * bpr + x] > 127 { n += 1 }
        if n >= minimo { return Int(Double(y) * Double(img.height) / Double(h)) }
    }
    return nil
}

func rosto(_ img: CGImage) throws -> [Int]? {
    let req = VNDetectFaceRectanglesRequest()
    try VNImageRequestHandler(cgImage: img).perform([req])
    guard let f = req.results?.max(by: { $0.boundingBox.width < $1.boundingBox.width }) else { return nil }
    let b = f.boundingBox, W = Double(img.width), H = Double(img.height)
    return [Int(b.minX * W), Int((1 - b.maxY) * H), Int(b.width * W), Int(b.height * H)]
}

let args = CommandLine.arguments
guard args.count == 2 else {
    print("uso: medir <pasta_de_frames>")
    exit(1)
}
for url in frames(args[1]) {
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
          let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { continue }
    let t = (try? topoPessoa(img)) ?? nil
    let r = (try? rosto(img)) ?? nil
    let topo = t.map { String($0) } ?? "null"
    let rs = r.map { "[\($0.map(String.init).joined(separator: ", "))]" } ?? "null"
    print("{\"arquivo\": \"\(url.lastPathComponent)\", \"topo\": \(topo), \"rosto\": \(rs)}")
}
