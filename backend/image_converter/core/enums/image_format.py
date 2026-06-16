from enum import Enum

class ImageFormat(Enum):
    JPEG = "JPEG"
    PNG = "PNG"
    ICO = "ICO"
    AVIF = "AVIF"
    PDF = "PDF"

    @classmethod
    def from_string(cls, value: str) -> "ImageFormat":
        """
        Converts a string to an ImageFormat enum member.
        Raises a ValueError if the format is not supported.
        """
        try:
            return cls[value.upper()]
        except KeyError:
            raise ValueError(f"Unsupported image format: '{value}'")

    def get_file_extension(self) -> str:
        """
        Returns the file extension associated with the image format.
        """
        return IMAGE_FORMAT_EXTENSIONS[self.name]

                                                 
IMAGE_FORMAT_EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "ICO": ".ico",
    "AVIF": ".avif",
    "PDF": ".pdf",
}
