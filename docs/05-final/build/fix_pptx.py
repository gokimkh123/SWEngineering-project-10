"""pptxgenjs 출력 후처리: 한글 단어 중간 줄바꿈 막기 (모든 문단 eaLnBrk=0). 사용: python fix_pptx.py in.pptx out.pptx"""
import re, sys, zipfile
src, dst = sys.argv[1], sys.argv[2]
zin = zipfile.ZipFile(src)
zout = zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
n = 0
for item in zin.infolist():
    data = zin.read(item.filename)
    if re.match(r"ppt/(slides/slide|slideLayouts/slideLayout|slideMasters/slideMaster|presentation)[^/]*\.xml$", item.filename):
        x = data.decode("utf-8")
        x2 = re.sub(r"<a:p>(?!<a:pPr)", '<a:p><a:pPr eaLnBrk="0"/>', x)
        x2 = re.sub(r"<a:pPr(?![^>]*eaLnBrk)(?=[\s/>])", '<a:pPr eaLnBrk="0"', x2)
        x2 = re.sub(r"<a:(lvl[1-9]pPr|defPPr)(?![^>]*eaLnBrk)(?=[\s/>])", r'<a:\1 eaLnBrk="0"', x2)
        # 한국어 문단으로 표시해야 PowerPoint가 어절 단위로 줄을 바꾼다
        x2 = re.sub(r'(<a:(?:rPr|endParaRPr|defRPr)[^>]*?)lang="en-US"(?![^>]*altLang)', r'\1lang="ko-KR" altLang="en-US"', x2)
        n += x2 != x
        data = x2.encode("utf-8")
    zout.writestr(item, data)
zout.close()
print("fixed parts", n)
