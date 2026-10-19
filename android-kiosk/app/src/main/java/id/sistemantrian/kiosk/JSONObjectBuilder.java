package id.sistemantrian.kiosk;

final class JSONObjectBuilder {
    private final org.json.JSONObject json = new org.json.JSONObject();

    JSONObjectBuilder put(String key, Object value) {
        try {
            json.put(key, value);
            return this;
        } catch (org.json.JSONException e) {
            throw new IllegalStateException(e);
        }
    }

    org.json.JSONObject build() {
        return json;
    }
}
