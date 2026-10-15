from lib.sanatizer_tool import load_sanitizer_config, scrub_data


class Sanitizer:
    def __init__(self):
        self.config = load_sanitizer_config()

    def process(self, raw_input):
        """Standardized cleaning routine for all grid traffic."""
        clean_data = scrub_data(raw_input, self.config)
        print("[Sanitizer] Data packet scrubbed.")
        return clean_data


if __name__ == "__main__":
    print(Sanitizer().process("  <b>hello</b>; $x  "))
