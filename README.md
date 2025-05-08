# 💰 Wealth$cribe – Financial Data Extractor

Wealth$cribe is a smart, AI-powered Streamlit app that extracts and analyzes key financial data from company PDF reports. Whether the data is in tables or images, it uses Google Gemini and OCR to detect and visualize:

- ✅ Revenue
- ✅ Operating Profit
- ✅ Net Profit

It supports both scanned and text-based PDFs, giving users clean visuals and a financial chatbot to explore insights.

---

## 🌐 Live App

👉 [Click here to use the app] https://wealthscribe.streamlit.app/  

---

## 🚀 Features

- 📁 Upload financial PDF statements
- 🧠 AI-based data extraction using Google Gemini 1.5 Flash
- 🔍 OCR fallback for scanned documents
- 📊 Visual comparisons of quarterly vs annual metrics
- 💬 Built-in financial chatbot
- 🌿 Green + Black theme for a clean and modern UI

---

## ⚙️ Tech Stack

- [Streamlit](https://streamlit.io/)
- [pdfplumber](https://github.com/jsvine/pdfplumber)
- [pytesseract](https://github.com/madmaze/pytesseract)
- [Google Generative AI](https://ai.google.dev/)
- [Matplotlib](https://matplotlib.org/)
- [Pillow (PIL)](https://python-pillow.org/)

---

## 🧑‍💻 Local Setup

1. **Clone the repo**

```bash
git clone https://github.com/Dhruvpatel50/financial-data-extractor.git
cd financial-data-extractor
```

2. **Install Dependencies**
```bash
pip install -r requirements.txt
```

3. **Run the App**
```bash
streamlit run mined.py
```
---

## 🤝 Contributing

Contributions are welcome! Please open an issue or pull request for suggestions, features, or bug fixes.

1. Fork the repository
2. Create a new branch
3. Commit your changes
4. Open a PR
