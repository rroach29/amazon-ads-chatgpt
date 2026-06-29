from fastapi import APIRouter, Header

from auth import verify_key
from amazon_ads import create_report, get_report_status, download_report_data

router = APIRouter()


@router.post("/sp-campaigns")
def create_sp_campaign_report(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return create_report("campaigns")


@router.post("/sp-search-terms")
def create_sp_search_terms_report(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return create_report("search_terms")


@router.post("/analyze")
def analyze_amazon_ads_account(x_api_key: str = Header(...)):
    verify_key(x_api_key)

    campaign_report = create_report("campaigns")
    search_report = create_report("search_terms")

    return {
        "status": "PENDING",
        "message": "Reports created. Wait 1-3 minutes, then collect the dashboard.",
        "campaignReportId": campaign_report.get("reportId"),
        "searchTermReportId": search_report.get("reportId"),
        "campaignReport": campaign_report,
        "searchTermReport": search_report,
    }


@router.get("/{report_id}")
def report_status(report_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_report_status(report_id)

@router.get("/{report_id}/download")
def download_report(report_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return download_report_data(report_id)
