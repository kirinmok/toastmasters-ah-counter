#!/usr/bin/env swift
// macOS Vision OCR — 輸出 JSON [{text, x, y, w, h}]
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("Usage: ocr <image_path>\n".data(using: .utf8)!)
    exit(2)
}

let url = URL(fileURLWithPath: args[1])
guard let nsImage = NSImage(contentsOf: url),
      let tiff = nsImage.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let cgImage = bitmap.cgImage else {
    FileHandle.standardError.write("Cannot load image\n".data(using: .utf8)!)
    exit(3)
}

let imgW = cgImage.width
let imgH = cgImage.height

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hant", "en-US"]

try handler.perform([request])
let observations = (request.results ?? []) as [VNRecognizedTextObservation]

// 輸出 JSON: [{text, x, y, w, h}]  座標已歸一化到 0-1
var items: [[String: Any]] = []
for obs in observations {
    guard let txt = obs.topCandidates(1).first?.string else { continue }
    let box = obs.boundingBox  // (origin: x,y, size: w,h), y 從下開始
    // 轉成「y 從上往下」的座標
    let yTop = 1.0 - box.origin.y - box.size.height
    items.append([
        "text": txt,
        "x": box.origin.x,
        "y": yTop,
        "w": box.size.width,
        "h": box.size.height,
    ])
}

let data = try JSONSerialization.data(withJSONObject: items, options: [])
print(String(data: data, encoding: .utf8)!)
