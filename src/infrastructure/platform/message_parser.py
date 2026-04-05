class MessageParserError(Exception):
    pass


class MessageParser:
    async def extract_first_image_path(self, event) -> str:
        message = getattr(getattr(event, "message_obj", None), "message", None)
        if not message:
            raise MessageParserError("消息中没有可解析的图片。")

        for component in message:
            if component.__class__.__name__ != "Image":
                continue
            converter = getattr(component, "convert_to_file_path", None)
            if converter is None:
                continue
            return await converter()

        raise MessageParserError("请在命令中附带一张比赛截图。")

