import cn.hutool.json.JSONUtil;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.giga.nexas.dto.bsdx.Bsdx;
import com.giga.nexas.service.BsdxBinService;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/**
 * CLI replacement of NeXAS_DX's JUnit BSDX round-trip tests (TestMek/TestWaz/TestSpm/TestGrp/TestBin/TestDat).
 * Same pipeline: BsdxBinService.parse -> hutool JSONUtil.toJsonStr -> Jackson readValue -> BsdxBinService.generate -> byte compare.
 *
 * Usage: java RoundTrip <gameBsdxDir> <outDir> [ext ...]
 *   JSON written to <outDir>/json/<ext>/<name>.<ext>.json, regenerated binary to <outDir>/gen/<ext>/
 */
public class RoundTrip {
    static final Map<String, String> CLS = Map.of(
            "mek", "com.giga.nexas.dto.bsdx.mek.Mek",
            "waz", "com.giga.nexas.dto.bsdx.waz.Waz",
            "spm", "com.giga.nexas.dto.bsdx.spm.Spm",
            "grp", "com.giga.nexas.dto.bsdx.grp.Grp",
            "bin", "com.giga.nexas.dto.bsdx.bin.Bin",
            "dat", "com.giga.nexas.dto.bsdx.dat.Dat");

    public static void main(String[] args) throws Exception {
        Path game = Paths.get(args[0]);
        Path out = Paths.get(args[1]);
        List<String> exts = args.length > 2 ? Arrays.asList(args).subList(2, args.length)
                : List.of("mek", "waz", "spm", "grp", "dat", "bin");
        BsdxBinService svc = new BsdxBinService();
        ObjectMapper mapper = new ObjectMapper();
        mapper.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        StringBuilder summary = new StringBuilder();
        for (String ext : exts) {
            Path dir = game.resolve(ext);
            Path jdir = out.resolve("json").resolve(ext), gdir = out.resolve("gen").resolve(ext);
            Files.createDirectories(jdir);
            Files.createDirectories(gdir);
            Class<?> cls = Class.forName(CLS.get(ext));
            int total = 0, match = 0, parseFail = 0, genFail = 0, mismatch = 0;
            List<String> details = new ArrayList<>();
            List<Path> files = new ArrayList<>();
            try (DirectoryStream<Path> ds = Files.newDirectoryStream(dir, "*." + ext)) { ds.forEach(files::add); }
            Collections.sort(files);
            for (Path f : files) {
                total++;
                String name = f.getFileName().toString();
                String base = name.substring(0, name.lastIndexOf('.'));
                Object obj;
                try {
                    obj = svc.parse(f.toString(), "windows-31j").getData();
                } catch (Throwable e) {
                    parseFail++;
                    details.add("PARSE_FAIL " + name + " : " + e);
                    continue;
                }
                try {
                    String json = JSONUtil.toJsonStr(obj);
                    Path jp = jdir.resolve(base + "." + ext + ".json");
                    Files.writeString(jp, json, StandardCharsets.UTF_8);
                    Bsdx back = (Bsdx) mapper.readValue(json, cls);
                    Path gp = gdir.resolve(name + ".generated");
                    svc.generate(gp.toString(), back, "windows-31j");
                    byte[] a = Files.readAllBytes(f), b = Files.readAllBytes(gp);
                    if (Arrays.equals(a, b)) { match++; }
                    else {
                        mismatch++;
                        int i = 0, n = Math.min(a.length, b.length);
                        while (i < n && a[i] == b[i]) i++;
                        details.add(String.format("MISMATCH %s orig=%d gen=%d firstDiff=0x%x", name, a.length, b.length, i));
                    }
                } catch (Throwable e) {
                    genFail++;
                    details.add("JSON/GEN_FAIL " + name + " : " + e);
                }
            }
            String line = String.format("%s: total=%d match=%d mismatch=%d parseFail=%d genFail=%d", ext, total, match, mismatch, parseFail, genFail);
            System.out.println(line);
            details.forEach(d -> System.out.println("   " + d));
            summary.append(line).append('\n');
            details.forEach(d -> summary.append("   ").append(d).append('\n'));
        }
        Files.writeString(out.resolve("summary.txt"), summary.toString(), StandardCharsets.UTF_8);
    }
}
