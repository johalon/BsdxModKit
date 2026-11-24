import cn.hutool.json.JSONUtil;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.giga.nexas.dto.bsdx.Bsdx;
import com.giga.nexas.service.BheBinService;
import com.giga.nexas.service.BsdxBinService;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Small CLI used by the Phase 3A port build (mods/phase3a_tsukuyomi/build_phase3a.py).
 *  b2j <bsdx|bhe> <file> <out.json>      parse -> hutool JSON (same JSON flavour as RoundTrip)
 *  j2b <in.json> <out.bin>               JSON (Jackson) -> BSDX generate; then re-parse + re-generate must be byte-identical
 *  spm <bhe.spm> <out.spm>               BHE spm -> BSDX spm via TransMeka.transSprite (with project hitbox fix)
 *  Several jobs can be given in one run separated by ';' tokens. */
public class PortTool {
  static final Map<String, String> CLS = Map.of(
      "mek", "com.giga.nexas.dto.bsdx.mek.Mek", "waz", "com.giga.nexas.dto.bsdx.waz.Waz",
      "spm", "com.giga.nexas.dto.bsdx.spm.Spm", "grp", "com.giga.nexas.dto.bsdx.grp.Grp",
      "bin", "com.giga.nexas.dto.bsdx.bin.Bin", "dat", "com.giga.nexas.dto.bsdx.dat.Dat");
  static BsdxBinService ds = new BsdxBinService(); static BheBinService hs = new BheBinService();
  static ObjectMapper om = new ObjectMapper();
  public static void main(String[] a) throws Exception {
    om.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    List<String> cur = new ArrayList<>(); int fails = 0;
    List<String> all = new ArrayList<>(Arrays.asList(a)); all.add(";");
    for (String t : all) {
      if (!t.equals(";")) { cur.add(t); continue; }
      if (cur.isEmpty()) continue;
      try { run(cur); } catch (Throwable e) { Throwable c = e; while (c.getCause() != null) c = c.getCause(); System.out.println("FAIL " + cur + " : " + c); c.printStackTrace(System.out); fails++; }
      cur = new ArrayList<>();
    }
    if (fails > 0) System.exit(1);
  }
  static String ext(String f) { String n = Paths.get(f).getFileName().toString().toLowerCase(); if (n.endsWith(".json")) n = n.substring(0, n.length() - 5); return n.substring(n.lastIndexOf('.') + 1); }
  static void run(List<String> c) throws Exception {
    switch (c.get(0)) {
      case "b2j": {
        Object o = (c.get(1).equals("bhe") ? hs.parse(c.get(2), "windows-31j") : ds.parse(c.get(2), "windows-31j")).getData();
        Files.writeString(Paths.get(c.get(3)), JSONUtil.toJsonStr(o), StandardCharsets.UTF_8);
        System.out.println("b2j " + c.get(2)); break; }
      case "j2b": {
        String e = ext(c.get(2));
        Bsdx obj = (Bsdx) om.readValue(Files.readString(Paths.get(c.get(1)), StandardCharsets.UTF_8), Class.forName(CLS.get(e)));
        if (obj.getExtensionName() == null) obj.setExtensionName(e);
        ds.generate(c.get(2), obj, "windows-31j");
        check(c.get(2)); System.out.println("j2b " + c.get(2) + " " + Files.size(Paths.get(c.get(2))) + " B (re-parse/regen identical)"); break; }
      case "spm": {
        Object src = hs.parse(c.get(1), "windows-31j").getData();
        Class<?> tm = Class.forName("com.giga.nexas.bhe2bsdx.steps.TransMeka");
        Method m = tm.getDeclaredMethod("transSprite", com.giga.nexas.dto.bhe.spm.Spm.class); m.setAccessible(true);
        Bsdx dst = (Bsdx) m.invoke(null, src); dst.setExtensionName("spm");
        ds.generate(c.get(2), dst, "windows-31j");
        check(c.get(2)); System.out.println("spm " + c.get(2) + " " + Files.size(Paths.get(c.get(2))) + " B (re-parse/regen identical)"); break; }
      default: throw new IllegalArgumentException(c.get(0));
    }
  }
  /** parse with BSDX parser, regenerate, require identical bytes */
  static void check(String f) throws Exception {
    Bsdx back = (Bsdx) ds.parse(f, "windows-31j").getData();
    Path g = Files.createTempFile("pt", "." + ext(f));
    ds.generate(g.toString(), back, "windows-31j");
    if (!Arrays.equals(Files.readAllBytes(Paths.get(f)), Files.readAllBytes(g))) throw new IllegalStateException("regen mismatch " + f);
    Files.delete(g);
  }
}
