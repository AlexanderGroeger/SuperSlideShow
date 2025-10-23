import os
import yaml

class SlideManager:
    def __init__(self, slides_folder):
        self.slides_folder = slides_folder
        self.slides = self.load_slides()

    def load_slides(self):
        slides = []
        for file in os.listdir(self.slides_folder):
            if file.endswith(".yaml"):
                path = os.path.join(self.slides_folder, file)
                with open(path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    slides.append({
                        "name": data.get("name", os.path.splitext(file)[0]),
                        "preview": data.get("preview"),  # preview image or video
                        "content": data
                    })
        return slides

    def get_slide_by_name(self, name):
        for slide in self.slides:
            if slide["name"] == name:
                return slide
        return None
