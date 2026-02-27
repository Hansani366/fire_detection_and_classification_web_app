# 🔥 Fire Detection Vision System

## 📌 Project Description

This project is a demonstration of an integrated vision system for fire detection.  
It combines:

- **YOLO** for real-time object detection  
- **Vision-Language Model (VLM)** for image captioning and visual reasoning  

The system captures live camera input from a web interface, performs object detection using YOLO, and generates descriptive captions using a VLM model. Both outputs are displayed on the same web page.

---

## 🏗️ System Architecture

The project follows a modular, microservices-based architecture to ensure scalability, flexibility, and easier maintenance.

---

## 📁 Project Structure

- **`frontend/`**  
  Web-based user interface that:
  - Captures live camera feed  
  - Displays YOLO detection results (bounding boxes)  
  - Shows VLM-generated captions  

- **`yolo-service/`**  
  Backend service responsible for object detection.
  - Uses **YOLOv11** for detecting fire-related objects  
  - Returns bounding boxes and confidence scores  

- **`vlm-service/`**  
  Backend service responsible for visual reasoning.
  - Uses **Moondream VLM** for image captioning  
  - Generates descriptive insights about detected scenes  

---

## 🚀 Key Features

- Real-time webcam streaming  
- Fire-related object detection  
- AI-powered scene understanding  
- Modular service-based design  
- Dockerized deployment support  

---

## 🛠️ Technologies Used

- YOLOv11  
- Moondream VLM  
- Docker  
- Web frontend (live camera streaming)  
