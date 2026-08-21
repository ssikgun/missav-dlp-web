import os


def configured_browser_url():
    return os.environ.get('TEDDY_BROWSER_URL', '').strip()


def install(core):
    @core.app.route('/api/browser/config', methods=['GET'])
    def teddy_browser_config():
        return core.jsonify({
            'url': configured_browser_url(),
        })
