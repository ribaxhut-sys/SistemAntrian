package id.sistemantrian.kiosk;

/** Server menjawab 4xx: permintaan ditolak, bukan server rusak. */
final class PenolakanServer extends IllegalStateException {
    final int kode;

    PenolakanServer(int kode, String detail) {
        super(detail);
        this.kode = kode;
    }
}
