// Local screenshot OCR. One image on stdin; JSON on stdout; no image files.
import Foundation
import Vision
import ImageIO

do {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard data.count <= 16 * 1024 * 1024,
          let source = CGImageSourceCreateWithData(data as CFData, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
          image.width * image.height <= 20_000_000 else {
        throw NSError(domain: "PhoneUseOCR", code: 1)
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = CommandLine.arguments.contains("--fast") ? .fast : .accurate
    request.recognitionLanguages = ["en-US"]
    request.usesLanguageCorrection = false
    let start = ProcessInfo.processInfo.systemUptime
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
    let elapsed = (ProcessInfo.processInfo.systemUptime - start) * 1000
    let lines: [[String: Any]] = (request.results ?? []).compactMap { observation in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let r = observation.boundingBox
        var words: [[String: Any]] = []
        candidate.string.enumerateSubstrings(in: candidate.string.startIndex..<candidate.string.endIndex,
                                             options: [.byWords]) { word, range, _, _ in
            if let word = word, let bounds = try? candidate.boundingBox(for: range) {
                let b = bounds.boundingBox
                words.append(["text": word, "box": [b.minX, 1 - b.maxY, b.maxX, 1 - b.minY]])
            }
        }
        // Vision starts at bottom-left; PhoneUse/WDA start at top-left.
        return ["text": candidate.string, "confidence": candidate.confidence, "words": words,
                "box": [r.minX, 1 - r.maxY, r.maxX, 1 - r.minY]]
    }
    let result: [String: Any] = ["width_px": image.width, "height_px": image.height,
                                "recognition_ms": elapsed, "lines": lines]
    FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]))
} catch {
    // Do not print images, recognized text, or device data on failure.
    FileHandle.standardError.write(Data("Local OCR failed\n".utf8))
    exit(1)
}
