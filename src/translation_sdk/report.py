import pandas as pd
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from typing import List, Dict
from .workflow import WorkflowResult
import logging

logger = logging.getLogger(__name__)

# Register Chinese Font
try:
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    CHINESE_FONT = 'STSong-Light'
except Exception as e:
    logger.warning(f"Failed to register Chinese font: {e}. Using Helvetica.")
    CHINESE_FONT = 'Helvetica'

class ReportGenerator:
    def __init__(self, results: List[WorkflowResult]):
        self.results = results
        # Flatten the data for DataFrame
        data = []
        for r in results:
            item = {
                "segment_id": r.segment_id,
                "original": r.original,
                "translation_a": r.translation_a,
                "score_a_total": r.eval_a.total_score if r.eval_a else 0,
                "score_a_accuracy": r.eval_a.accuracy if r.eval_a else 0,
                "score_a_fluency": r.eval_a.fluency if r.eval_a else 0,
                "score_a_consistency": r.eval_a.consistency if r.eval_a else 0,
                "score_a_terminology": r.eval_a.terminology if r.eval_a else 0,
                "score_a_completeness": r.eval_a.completeness if r.eval_a else 0,
                "translation_c": r.translation_c,
                "score_c_total": r.eval_c.total_score if r.eval_c else 0,
                "score_c_accuracy": r.eval_c.accuracy if r.eval_c else 0,
                "score_c_fluency": r.eval_c.fluency if r.eval_c else 0,
                "score_c_consistency": r.eval_c.consistency if r.eval_c else 0,
                "score_c_terminology": r.eval_c.terminology if r.eval_c else 0,
                "score_c_completeness": r.eval_c.completeness if r.eval_c else 0,
                "selected_model": r.selected_model
            }
            data.append(item)
        self.df = pd.DataFrame(data)

    def generate_excel(self, output_path: str):
        try:
            self.df.to_excel(output_path, index=False)
            logger.info(f"Excel report saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to generate Excel report: {e}")

    def generate_pdf(self, output_path: str, metadata: Dict[str, str] = None):
        try:
            doc = SimpleDocTemplate(
                output_path, 
                pagesize=A4,
                rightMargin=2*cm, leftMargin=2*cm,
                topMargin=2*cm, bottomMargin=2*cm
            )
            elements = []
            
            # Styles
            styles = getSampleStyleSheet()
            # Define Custom Styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontName=CHINESE_FONT,
                fontSize=24,
                leading=30,
                alignment=0, # Left
                textColor=colors.HexColor('#2F5597')
            )
            
            header_style = ParagraphStyle(
                'CustomHeader',
                parent=styles['Normal'],
                fontName=CHINESE_FONT,
                fontSize=10,
                alignment=1, # Center
                textColor=colors.grey
            )
            
            section_title_style = ParagraphStyle(
                'SectionTitle',
                parent=styles['Heading2'],
                fontName=CHINESE_FONT,
                fontSize=16,
                textColor=colors.HexColor('#2F5597'),
                spaceBefore=12,
                spaceAfter=6
            )
            
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontName=CHINESE_FONT,
                fontSize=10,
                leading=14
            )
            
            bold_style = ParagraphStyle(
                'CustomBold',
                parent=styles['Normal'],
                fontName=CHINESE_FONT,
                fontSize=10,
                leading=14,
                textColor=colors.black
            )

            # --- Header Content ---
            elements.append(Paragraph("此文件由译曲同工提供翻译服务", header_style))
            elements.append(Paragraph("更多信息请访问 aitranspro.com", header_style))
            elements.append(Paragraph("——内容仅供内部评估与试阅——", header_style))
            elements.append(Spacer(1, 1*cm))
            
            # --- Title & Metadata ---
            elements.append(Paragraph("翻译质量评估报告", title_style))
            filename = metadata.get("filename", "Unknown File") if metadata else "Unknown File"
            elements.append(Paragraph(filename, ParagraphStyle('SubTitle', parent=normal_style, fontSize=14, textColor=colors.grey)))
            elements.append(Spacer(1, 1*cm))
            
            # Metadata Grid
            source_lang = metadata.get("source_lang", "Unknown") if metadata else "Unknown"
            target_lang = metadata.get("target_lang", "Unknown") if metadata else "Unknown"
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            task_id = metadata.get("task_id", "161") if metadata else "161"
            
            meta_data = [
                [f"源语言: {source_lang}", f"目标语言: {target_lang}"],
                [f"日期: {date_str}", f"任务ID: {task_id}"]
            ]
            meta_table = Table(meta_data, colWidths=[8*cm, 8*cm])
            meta_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ]))
            elements.append(meta_table)
            elements.append(Spacer(1, 1*cm))
            
            # --- Model Explanation ---
            elements.append(Paragraph("模型说明", section_title_style))
            model_data = [
                ["别名", "角色"],
                ["A", "翻译模型"],
                ["B", "润色模型 (优化)"], # Mapping C to B for display as per user request/image implication
                ["C", "评估模型"] # My B is Evaluator
            ]
            # Wait, user image shows: A=翻译, B=润色, C=评估. 
            # My workflow: A=Translate, C=Optimize, B=Evaluate.
            # So I should map: My A -> A, My C -> B, My B -> C.
            
            model_table = Table(model_data, colWidths=[6*cm, 10*cm])
            model_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2F5597')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.whitesmoke])
            ]))
            elements.append(model_table)
            elements.append(Spacer(1, 1*cm))
            
            # --- Comprehensive Score ---
            elements.append(Paragraph("模型综合评分", section_title_style))
            
            # Calculate averages
            avg_a = self.df[['score_a_accuracy', 'score_a_fluency', 'score_a_consistency', 'score_a_terminology', 'score_a_completeness']].mean()
            avg_c = self.df[['score_c_accuracy', 'score_c_fluency', 'score_c_consistency', 'score_c_terminology', 'score_c_completeness']].mean()
            total_a = self.df['score_a_total'].mean()
            total_c = self.df['score_c_total'].mean()
            
            score_data = [
                ["评分维度", "A\n(翻译)", "B\n(润色)"],
                ["准确性", f"{avg_a['score_a_accuracy']:.2f}", f"{avg_c['score_c_accuracy']:.2f}"],
                ["流畅性", f"{avg_a['score_a_fluency']:.2f}", f"{avg_c['score_c_fluency']:.2f}"],
                ["一致性", f"{avg_a['score_a_consistency']:.2f}", f"{avg_c['score_c_consistency']:.2f}"],
                ["术语准确性", f"{avg_a['score_a_terminology']:.2f}", f"{avg_c['score_c_terminology']:.2f}"],
                ["完整性", f"{avg_a['score_a_completeness']:.2f}", f"{avg_c['score_c_completeness']:.2f}"],
                ["综合评分", f"{total_a:.2f}", f"{total_c:.2f}"]
            ]
            
            score_table = Table(score_data, colWidths=[6*cm, 5*cm, 5*cm])
            score_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2F5597')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('ROWBACKGROUNDS', (0, 1), (-2, -1), [colors.white, colors.whitesmoke]), # Alternating rows
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FFF2CC')), # Last row (Total) yellow
                ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),
            ]))
            elements.append(score_table)
            elements.append(PageBreak())
            
            # --- Detailed Segment Evaluation ---
            elements.append(Paragraph("详细段落评估", section_title_style))
            
            for i, r in enumerate(self.results):
                # Segment Header
                elements.append(Paragraph(f"段落 {i+1}", ParagraphStyle('SegTitle', parent=normal_style, fontSize=12, textColor=colors.HexColor('#2F5597'))))
                
                # Helper to truncate text
                def truncate_text(text, limit=1000):
                    if len(text) > limit:
                        return text[:limit] + "..."
                    return text

                # Original Text
                from xml.sax.saxutils import escape
                elements.append(Paragraph(f"原文: {escape(truncate_text(r.original))}", normal_style))
                elements.append(Spacer(1, 6))
                
                # Comparison Table
                comp_data = [
                    ["模型", "角色", "译文", "评分"],
                    ["A", "翻译", Paragraph(escape(truncate_text(r.translation_a)), normal_style), f"{r.eval_a.total_score:.2f}" if r.eval_a else "0"],
                    ["B", "润色", Paragraph(escape(truncate_text(r.translation_c)), normal_style), f"{r.eval_c.total_score:.2f}" if r.eval_c else "0"]
                ]
                
                comp_table = Table(comp_data, colWidths=[2*cm, 2*cm, 10*cm, 2*cm])
                comp_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0070C0')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                elements.append(comp_table)
                elements.append(Spacer(1, 6))
                
                # Evaluation Details
                elements.append(Paragraph("评估详情:", bold_style))
                
                # Check for failures
                is_failed_a = (r.eval_a and r.eval_a.total_score == 0) or (r.eval_a and "Untranslated" in r.eval_a.suggestions)
                if is_failed_a:
                    failure_style = ParagraphStyle('Failure', parent=bold_style, textColor=colors.red)
                    elements.append(Paragraph("⚠️ 严重错误: 该段落未完成翻译 (Untranslated)", failure_style))

                # Eval A
                elements.append(Paragraph(f"• C -> A: {r.eval_a.total_score if r.eval_a else 0}/10", normal_style))
                # Note: I don't have "Reason" separate from "Suggestions" in my data structure.
                # I will use suggestions as the main feedback.
                suggestion_a = r.eval_a.suggestions if r.eval_a else "无"
                elements.append(Paragraph(f"优化建议: {escape(suggestion_a)}", normal_style))
                
                # Eval C (B in report)
                elements.append(Paragraph(f"• C -> A -> B: {r.eval_c.total_score if r.eval_c else 0}/10", normal_style))
                suggestion_c = r.eval_c.suggestions if r.eval_c else "无"
                elements.append(Paragraph(f"优化建议: {escape(suggestion_c)}", normal_style))
                
                elements.append(Spacer(1, 12))
                
                # Add page break every few segments? Or let flow.
                # Let flow.
            
            doc.build(elements)
            logger.info(f"PDF report saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to generate PDF report: {e}")
            import traceback
            traceback.print_exc()
