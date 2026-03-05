# auth

# jwt: jwt封裝
'''
    使用SOLID原則中的單一職責原則 SRP
    jwt.key_manager: 金鑰管理
    jwt.jwt_service: jwt服務
'''

# login_interface: 登入介面
'''
    使用SOLID原則中的介面隔離原則 ISP
    每新增一個login方式
    需要新增一個login service
    並在login controller中新增一個login method
    並在login router中新增一個login route
'''
