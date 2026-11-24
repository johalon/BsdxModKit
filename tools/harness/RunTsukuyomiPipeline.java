import com.giga.nexas.service.BheBinService;
import com.giga.nexas.service.BsdxBinService;
import java.lang.reflect.Method;
import java.nio.file.*;
import java.util.*;
/** Runs the private steps of NeXAS_DX's experimental TransMeka (BHE->BSDX) on one BHE mech and tries to
 *  GENERATE BSDX binaries from the results (the original pipeline never writes anything).
 *  Usage: RunTsukuyomiPipeline <game/bhe> <outDir> [mech=tsukuyomi] */
public class RunTsukuyomiPipeline {
  public static void main(String[] a) throws Exception {
    Path bhe = Paths.get(a[0]), out = Paths.get(a[1]); String name = a.length > 2 ? a[2] : "tsukuyomi";
    Files.createDirectories(out);
    BheBinService hs = new BheBinService(); BsdxBinService ds = new BsdxBinService();
    Class<?> tm = Class.forName("com.giga.nexas.bhe2bsdx.steps.TransMeka");
    Object[][] steps = {
      {"transWaza", "waz/" + name + ".waz", com.giga.nexas.dto.bhe.waz.Waz.class, name + ".waz"},
      {"transSprite", "spm/" + name + ".spm", com.giga.nexas.dto.bhe.spm.Spm.class, name + ".spm"},
      {"transSprite", "spm/c_" + name + ".spm", com.giga.nexas.dto.bhe.spm.Spm.class, "c_" + name + ".spm"},
      {"transMeka", "mek/" + name + ".mek", com.giga.nexas.dto.bhe.mek.Mek.class, name + ".mek"},
    };
    for (Object[] st : steps) {
      String label = st[0] + " " + st[1];
      try {
        Object src = hs.parse(bhe.resolve((String) st[1]).toString(), "windows-31j").getData();
        Method m = tm.getDeclaredMethod((String) st[0], (Class<?>) st[2]); m.setAccessible(true);
        com.giga.nexas.dto.bsdx.Bsdx dst = (com.giga.nexas.dto.bsdx.Bsdx) m.invoke(null, src);
        if (dst instanceof com.giga.nexas.dto.bsdx.mek.Mek && Boolean.getBoolean("fixAi")) fixAi((com.giga.nexas.dto.bhe.mek.Mek) src, (com.giga.nexas.dto.bsdx.mek.Mek) dst);
        String ext = ((String) st[3]).substring(((String) st[3]).lastIndexOf('.') + 1);
        if (dst.getExtensionName() == null) dst.setExtensionName(ext);
        Path o = out.resolve((String) st[3]);
        ds.generate(o.toString(), dst, "windows-31j");
        // re-parse with the BSDX parser
        Object back = ds.parse(o.toString(), "windows-31j").getData();
        System.out.println("OK   " + label + " -> " + o.getFileName() + " (" + Files.size(o) + " B, re-parse OK)");
      } catch (Throwable e) {
        Throwable c = e; while (c.getCause() != null) c = c.getCause();
        System.out.println("FAIL " + label + " : " + c);
      }
    }
  }

  /** WORKAROUND: TransMeka's BeanUtil copy turns BHE CCpuEventMove/Attack into the BSDX *base* class (fields lost).
   *  Re-map each AI event via JSON into the BSDX subclass chosen by its type (bheInfoCollectionList -> bsdxInfoCollectionList).
   *  BHE-only fields (e.g. CCpuEventAttack.positionX/Y) are dropped. */
  static void fixAi(com.giga.nexas.dto.bhe.mek.Mek src, com.giga.nexas.dto.bsdx.mek.Mek dst) throws Exception {
    com.fasterxml.jackson.databind.ObjectMapper om = new com.fasterxml.jackson.databind.ObjectMapper();
    om.configure(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    List<com.giga.nexas.dto.bsdx.mek.Mek.MekAiInfo> list = new ArrayList<>();
    for (var ai : src.getMekAiInfoList()) {
      var d = new com.giga.nexas.dto.bsdx.mek.Mek.MekAiInfo();
      d.setAiTypeJapanese(ai.getAiTypeJapanese()); d.setAiTypeEnglish(ai.getAiTypeEnglish());
      for (var ev : ai.getCpuEventList()) {
        String json = cn.hutool.json.JSONUtil.toJsonStr(ev).replace("\"bheInfoCollectionList\"", "\"bsdxInfoCollectionList\"");
        d.getCpuEventList().add(om.readValue(json, com.giga.nexas.dto.bsdx.mek.mekcpu.CCpuEvent.class));
      }
      list.add(d);
    }
    dst.setMekAiInfoList(list);
  }
}
