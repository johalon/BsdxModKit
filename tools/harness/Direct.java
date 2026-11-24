import com.giga.nexas.dto.bsdx.Bsdx;
import com.giga.nexas.service.BsdxBinService;
import java.nio.file.*;
import java.util.*;
/** parse -> generate without JSON, to separate serializer issues from parser/generator issues. Usage: Direct <file>... */
public class Direct {
  public static void main(String[] a) throws Exception {
    BsdxBinService s = new BsdxBinService();
    Path tmp = Files.createTempDirectory("direct");
    for (String f : a) {
      Bsdx o = (Bsdx) s.parse(f, "windows-31j").getData();
      String n = Paths.get(f).getFileName().toString();
      Path g = tmp.resolve(n);
      s.generate(g.toString(), o, "windows-31j");
      byte[] x = Files.readAllBytes(Paths.get(f)), y = Files.readAllBytes(g);
      int i = 0; while (i < Math.min(x.length, y.length) && x[i] == y[i]) i++;
      System.out.println((Arrays.equals(x, y) ? "MATCH " : "MISMATCH ") + n + " " + x.length + "/" + y.length + " diff@0x" + Integer.toHexString(i));
    }
  }
}
