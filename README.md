# PDF 保單掃描檔自動命名工具

這個工具會讀取資料夾中的 PDF，嘗試從內容辨識：

- 客戶姓名
- 保單號碼（若有）
- 變更項目
- 日期（優先抓文件內日期，抓不到則用檔案修改日）

最後改名為：

`日期_客戶姓名_保單號碼_變更項目.pdf`

> 若辨識不到保單號碼，會自動省略該欄位。

## 安裝

```bash
python3 -m pip install pypdf pdf2image pytesseract
```

另外請先安裝 Tesseract OCR 主程式（系統層級）。

## 使用方式

先試跑（不改檔）：

```bash
python3 pdf_auto_renamer.py /你的/PDF資料夾 --dry-run --recursive
```

正式更名：

```bash
python3 pdf_auto_renamer.py /你的/PDF資料夾 --recursive
```

## 常用參數

- `--recursive`：遞迴子資料夾
- `--dry-run`：只看結果，不改檔
- `--no-ocr`：只讀 PDF 內嵌文字，不做 OCR
- `--no-backup`：不在目錄建立 `_backup_original_names` 備份

## 注意事項

- OCR 正確率取決於掃描品質、解析度、影像歪斜程度。
- 目前預設使用前幾頁做 OCR，主要適合保單異動/契約文件。
- 若文件格式固定，建議再客製化 `pdf_auto_renamer.py` 內的正則規則，提高姓名/保單號碼辨識率。
