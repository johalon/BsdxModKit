import cn.hutool.json.JSONUtil;
import com.giga.nexas.service.BheBinService;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
/** BHE: parse all mek/waz/spm/grp (dump JSON); for spm/grp also generate (direct, no JSON) and byte-compare.
 *  Usage: BheRoundTrip <game/bhe dir> <outDir> */
public class BheRoundTrip {
  public static void main(String[] a) throws Exception {
    BheBinService s = new BheBinService();
    Path game = Paths.get(a[0]), out = Paths.get(a[1]);
    for (String ext : List.of("grp", "mek", "waz", "spm")) {
      Path jd = out.resolve("json").resolve(ext), gd = out.resolve("gen").resolve(ext);
      Files.createDirectories(jd); Files.createDirectories(gd);
      List<Path> fs = new ArrayList<>();
      try (DirectoryStream<Path> ds = Files.newDirectoryStream(game.resolve(ext), "*." + ext)) { ds.forEach(fs::add); }
      Collections.sort(fs);
      int ok = 0, pf = 0, match = 0, mis = 0, gf = 0; List<String> det = new ArrayList<>();
      for (Path f : fs) {
        Object o;
        try { o = s.parse(f.toString(), "windows-31j").getData(); ok++; }
        catch (Throwable e) { pf++; det.add("PARSE_FAIL " + f.getFileName() + " " + e); continue; }
        Files.writeString(jd.resolve(f.getFileName() + ".json"), JSONUtil.toJsonStr(o), StandardCharsets.UTF_8);
        if (ext.equals("spm") || ext.equals("grp")) {
          try {
            Path g = gd.resolve(f.getFileName().toString());
            s.generate(g.toString(), (com.giga.nexas.dto.bhe.Bhe) o, "windows-31j");
            byte[] x = Files.readAllBytes(f), y = Files.readAllBytes(g);
            if (Arrays.equals(x, y)) match++; else { mis++; int i = 0; while (i < Math.min(x.length, y.length) && x[i] == y[i]) i++;
              det.add(String.format("MISMATCH %s %d/%d @0x%x", f.getFileName(), x.length, y.length, i)); }
          } catch (Throwable e) { gf++; det.add("GEN_FAIL " + f.getFileName() + " " + e); }
        }
      }
      System.out.printf("%s: total=%d parsed=%d parseFail=%d | gen match=%d mismatch=%d genFail=%d%n", ext, fs.size(), ok, pf, match, mis, gf);
      det.stream().limit(15).forEach(d -> System.out.println("   " + d));
      Files.write(out.resolve(ext + "_details.txt"), det, StandardCharsets.UTF_8);
    }
  }
}
